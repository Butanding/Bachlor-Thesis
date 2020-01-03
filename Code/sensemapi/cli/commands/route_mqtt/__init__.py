# system modules
import logging
import time
import collections
import io
from urllib.parse import urlparse

# internal modules
import sensemapi
from sensemapi.errors import (
    SenseMapiError,
    NoEmailError,
    NoUserError,
    NoPasswordError,
    OpenSenseMapAPIInvalidCredentialsError,
    OpenSenseMapAPIAuthenticationError,
)
from sensemapi.cli.commands.main import cli
from sensemapi.cli.commands.route_mqtt.queue import UploadQueue
from sensemapi.cli.commands.route_mqtt.config import (
    Configuration,
    BrokerSectionError,
)

# external modules
import pandas as pd
import click

logger = logging.getLogger(__name__)


def scheme_url(scheme):
    def url(arg):
        return urlparse(
            arg
            if arg.startswith("{}://".format(scheme))
            else "{}://{}".format(scheme, arg),
            scheme=scheme,
        )

    return url


@cli.command(
    # Due to a bug in click (https://github.com/pallets/click/issues/1253)
    # if we want to use the automatic environment variable feature AND a
    # command name that consists of two words, we cannot use a dash to separate
    # them but must use an underscore.
    name="route_mqtt",
    help="Route data from an MQTT broker to the OpenSenseMap",
)
@click.option(
    "-c",
    "--config",
    "configfiles",
    help="Add a configuration file to read. Can be specified multiple times.",
    type=click.Path(readable=True, exists=True, dir_okay=False),
    multiple=True,
    show_envvar=True,
    default=tuple(),
)
@click.option(
    "-b",
    "--broker",
    "cli_mqtt_brokers",
    help="add another MQTT broker to connect to. "
    "Supports user:pass@host:port format. "
    "Can be specified multiple times.",
    type=scheme_url("mqtt"),
    default=tuple(),
    multiple=True,
)
@click.option(
    "--opensensemap",
    help="OpenSenseMap access to use. "
    "Supports https://user:password@api.opensensemap.org format",
    type=scheme_url("https"),
    show_envvar=True,
    default="https://api.opensensemap.org",
)
@click.option(
    "--bundle-upload/--single-upload",
    "opensensemap_bundle_upload",
    help="bundle measurements of a single senseBox together. "
    "This is enabled by default and can help overcome "
    "the rate limiting of the OpenSenseMap. However, if you are not affected "
    "by the rate limiting, disabling this might be more sensible.",
    default=True,
)
@click.option(
    "--queue-length",
    "opensensemap_upload_queue_length",
    help="How many measurements to queue at max for OpenSenseMap upload",
    show_default=True,
    type=click.IntRange(min=1),
    default=100,
)
@click.option(
    "--min-interval",
    "per_sensor_upload_interval",
    help="Minimum amount of seconds to wait between uploads to sensors.",
    show_default=True,
    type=click.FloatRange(min=0),
)
@click.option(
    "--dry-run",
    help="Don't actually upload anything to the OpenSenseMap. "
    "This is handy for testing if your configuration is working as expected.",
    is_flag=True,
)
@click.option("-v", "--log-mqtt", help="Show MQTT log messages", is_flag=True)
@click.pass_context
def route_mqtt(
    ctx,
    cli_mqtt_brokers,
    configfiles,
    log_mqtt,
    opensensemap,
    opensensemap_upload_queue_length,
    opensensemap_bundle_upload,
    per_sensor_upload_interval,
    dry_run,
):
    config = Configuration()
    logger.debug("Reading configuration files {}".format(configfiles))
    config.read(configfiles)

    for broker in cli_mqtt_brokers:
        logger.debug("Adding {} to configuration".format(broker))
        section = config.add_section(
            "{prefix}:{hostname}".format(
                prefix=config.BROKER_SECTION_PREFIX, hostname=broker.hostname
            )
        )
        section["hostname"] = broker.hostname
        for attrib in ("port", "username", "password"):
            value = getattr(broker, attrib, None)
            if value is not None:
                section[attrib] = str(value)

    if "opensensemap" not in config:
        config.add_section("opensensemap")
    for attrib in ("username", "password", "hostname"):
        value = getattr(opensensemap, attrib, None)
        if value is not None:
            config["opensensemap"][attrib] = str(value)
    if per_sensor_upload_interval is not None:
        config["opensensemap"]["min-interval"] = str(
            per_sensor_upload_interval
        )

    buf = io.StringIO()
    config.write(buf)
    logger.debug("Configuration:\n{}".format(buf.getvalue().strip()))

    account = config.opensensemap_account

    upload_queue = UploadQueue(maxlen=opensensemap_upload_queue_length)
    upload_queue.account = account
    upload_queue.bundle = opensensemap_bundle_upload
    upload_queue.per_sensor_upload_interval = config["opensensemap"].getfloat(
        "min-interval", 0
    )

    def start_client(client):
        logger.info(
            "Starting MQTT client {client._client_id} connecting to "
            "broker {client._host}:{client._port}...".format(client=client)
        )

        def on_log(client, obj, level, string):
            logger.info(
                "Client {client._client_id} on "
                "{client._host}:{client._port}: {msg}".format(
                    client=client, msg=string
                )
            )

        if log_mqtt:
            client.on_log = on_log
        client.opensensemap_account = account
        client.opensensemap_upload_queue = upload_queue
        client.loop_start()
        return client

    try:
        clients = tuple(map(start_client, config.clients))
    except BrokerSectionError as e:
        raise click.ClickException(
            "Error setting up MQTT clients from "
            "configuration: {error}".format(error=e)
        )

    def close_clients():
        for client in clients:
            logger.debug(
                "disconnecting MQTT client {client._client_id}".format(
                    client=client
                )
            )
            client.disconnect()

    ctx.call_on_close(close_clients)

    if not clients:
        logger.info("No brokers defined. Using localhost.")
        section = config.add_section(
            "{prefix}:localhost".format(prefix=config.BROKER_SECTION_PREFIX)
        )
        section["hostname"] = "localhost"
        clients = tuple(map(start_client, config.clients))

    def upload_next_queued_dataset():
        dataset = next(upload_queue.dataset(), None)
        if not dataset:
            return
        logger.debug(
            "Processing dataset {dataset} queued "
            "for OpenSenseMap upload".format(dataset=dataset)
        )
        box_id, measurements = next(iter(dataset.items()))
        try:
            box = account.boxes.by_id[box_id]
        except KeyError:
            logger.error(
                "No such senseBox with id {box_id}.".format(box_id=box_id)
            )
            return
        if not measurements:
            logger.error(
                "Somehow, there are no measurements in {dataset}...".format(
                    dataset=dataset
                )
            )
            return
        if len(measurements) == 1:  # only one measurement
            sensor_id, (meas_time, measurement) = next(
                iter(measurements.items())
            )
            try:
                sensor = box.sensors.by_id[sensor_id]
            except KeyError:
                logger.error(
                    "senseBox '{box.name}' has no "
                    "sensor with id {sensor_id}".format(
                        box=box, sensor_id=sensor_id
                    )
                )
                return
            sensor.last_time = meas_time
            sensor.last_value = measurement
            if dry_run:
                logger.info(
                    "Would now upload measurement "
                    "{sensor.last_value} at time {sensor.last_time} "
                    "to sensor '{sensor.title}' "
                    "of senseBox '{sensor.box.name}'".format(sensor=sensor)
                )
            else:
                time_before_upload = time.time()
                try:
                    sensor.upload_measurement()
                    logger.info(
                        "Successfully uploaded measurement "
                        "{sensor.last_value} at time {sensor.last_time} "
                        "to sensor '{sensor.title}' "
                        "of senseBox '{sensor.box.name}' "
                        "within {time:.2f} seconds".format(
                            sensor=sensor,
                            time=time.time() - time_before_upload,
                        )
                    )
                except sensemapi.errors.SenseMapiError as e:
                    logger.error(
                        "Could not upload measurement "
                        "{sensor.last_value} at time {sensor.last_time} "
                        "to sensor '{sensor.title}' "
                        "of senseBox '{sensor.box.name}': {error}".format(
                            sensor=sensor, error=e
                        )
                    )
                    # TODO: re-queue the failed dataset?
        else:  # multiple measurements

            def dataset_to_records(ds):
                for box_id, meas in ds.items():
                    for sensor_id, (ts, m) in meas.items():
                        yield {"sensor_id": sensor_id, "time": ts, "value": m}

            df = pd.DataFrame.from_records(dataset_to_records(dataset))
            if dry_run:
                logger.debug(
                    "Would now upload multiple measurements:\n{}".format(df)
                )
            else:
                logger.debug("Uploading multiple measurements:\n{}".format(df))
                time_before_upload = time.time()
                try:
                    account.post_measurements(box.id, df)
                    logger.info(
                        "Successfully uploaded multiple measurements "
                        "to senseBox '{box.name}' within "
                        "{seconds:.2f} seconds".format(
                            box=box, seconds=time.time() - time_before_upload
                        )
                    )
                except sensemapi.errors.SenseMapiError as e:
                    logger.error(
                        "Error posting multiple measurements: {}".format(e)
                    )

    time_last_account_update = 0
    while True:
        # Every couple of minutes, update the account
        if time.time() - time_last_account_update > 600:
            try:
                logger.info("Retrieving senseBoxes of OpenSenseMap account...")
                account.get_own_boxes()
                logger.info(
                    "OpenSenseMap account has {n} senseBoxes: {boxes}".format(
                        n=len(account.boxes),
                        boxes=", ".join(map(repr, account.boxes.by_name)),
                    )
                )
                time_last_account_update = time.time()
            except (
                NoEmailError,
                NoUserError,
                NoPasswordError,
                OpenSenseMapAPIInvalidCredentialsError,
                OpenSenseMapAPIAuthenticationError,
            ) as e:
                raise click.ClickException(
                    "Cannot sign in to openSenseMap: {error}".format(error=e)
                )
            except SenseMapiError as e:
                logger.error(
                    "Could not retrieve senseBoxes "
                    "of OpenSenseMap account: {}".format(e)
                )
        upload_next_queued_dataset()
        time.sleep(0.1)

    ctx.fail("Routing MQTT data to the OpenSenseMap is not yet implemented!")
