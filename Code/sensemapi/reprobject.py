# system modules
import inspect
import json
import re
import warnings

# internal modules

# external modules


class ReprObject(object):  # pragma: no cover
    """
    Simple base class that defines a :any:`__repr__` method based on an
    object's ``__init__`` arguments and properties that are named equally.
    Subclasses of :any:`ReprObject` should thus make sure to have properties
    that are named equally as their ``__init__`` arguments.
    """

    @classmethod
    def _full_variable_path(cls, var):
        """ Get the full string of a variable

        Args:
            var (any): The variable to get the full string from

        Returns:
            str : The full usable variable string including the module
        """
        if inspect.ismethod(var):  # is a method
            string = "{module}.{cls}.{name}".format(
                name=var.__name__,
                cls=var.__self__.__class__.__name__,
                module=var.__module__,
            )
        else:
            name = var.__name__
            module = var.__module__
            if module == "builtins":
                string = name
            else:
                string = "{module}.{name}".format(name=name, module=module)
        return string

    @property
    def init_arguments(self):
        init_args = {}
        for arg in inspect.getfullargspec(self.__init__).args[1:]:
            try:
                init_args[arg] = getattr(self, arg)
            except AttributeError:
                warnstr = (
                    "class {cls} has no property or attribute "
                    "'{arg}' like the argument in its __init__. "
                ).format(cls=classname, arg=arg)
                warnings.warn(warnstr)
        return init_args

    def to_json_fallback(self, x):
        try:
            return x.to_json()
        except (AttributeError):
            return str(x)

    def to_json(self):
        return json.loads(
            json.dumps(self.init_arguments, default=self.to_json_fallback)
        )

    @classmethod
    def from_json(cls, d):
        init_argspec = inspect.getfullargspec(self.__init__)
        init_args = {
            arg: default
            for arg, default in zip(
                init_argspec.args[1:], init_argspec.defaults[1:]
            )
        }
        for k, v in d.items():
            if k in init_args:
                init_args[k] = v
        obj = cls(**init_args)
        return obj

    def update_from_json(self, d):
        for k, v in d.items():
            try:
                setattr(self, k, v)
            except AttributeError:
                pass

    def __repr__(self):
        """
        Python representation of this object

        Returns:
            str : a Python representation of this object based on its
            ``__init__`` arguments and corresponding properties.
        """
        indent = "    "
        # the current "full" classname
        classname = self._full_variable_path(self.__class__)

        # get a dict of {'argname':'property value'} from init arguments
        init_args = {}  # start with empty dict
        for arg in inspect.getfullargspec(self.__init__).args[1:]:
            try:
                attr = getattr(self, arg)  # get the attribute
                try:
                    string = self._full_variable_path(attr)
                except BaseException:
                    string = repr(attr)

                # indent the arguments
                init_args[arg] = re.sub(
                    string=string, pattern="\n", repl="\n" + indent
                )
            except AttributeError:  # no such attribute
                warnstr = (
                    "class {cls} has no property or attribute "
                    "'{arg}' like the argument in its __init__. "
                    "Cannot include argument '{arg}' into __repr__."
                ).format(cls=classname, arg=arg)
                warnings.warn(warnstr)

        # create "arg = {arg}" string list for reprformat
        args_kv = []
        for arg in init_args.keys():
            args_kv.append(indent + "{arg} = {{{arg}}}".format(arg=arg))

        # create the format string
        if args_kv:  # if there are arguments
            reprformatstr = "\n".join(
                ["{____classname}(", ",\n".join(args_kv), indent + ")"]
            )
        else:  # no arguments
            reprformatstr = "{____classname}()"

        # add classname to format args
        reprformatargs = init_args.copy()
        reprformatargs.update({"____classname": classname})

        reprstring = (reprformatstr).format(**reprformatargs)
        return reprstring
