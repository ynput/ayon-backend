import numbers
import os
import re
from typing import Any, Union

KEY_PATTERN = re.compile(r"(\{.*?[^{0]*\})")
KEY_PADDING_PATTERN = re.compile(r"([^:]+)\S+[><]\S+")
SUB_DICT_PATTERN = re.compile(r"([^\[\]]+)")
OPTIONAL_PATTERN = re.compile(r"(<.*?[^{0]*>)[^0-9]*?")


class TemplateMissingKey(Exception):
    """Exception for cases when key does not exist in template."""

    msg = "Template key does not exist: `{}`."

    def __init__(self, parents: list[str]):
        parent_join = "".join([f'["{key}"]' for key in parents])
        super().__init__(self.msg.format(parent_join))


class TemplateUnsolved(Exception):
    """Exception for unsolved template when strict is set to True."""

    msg = 'Template "{0}" is unsolved.{1}{2}'
    invalid_types_msg = " Keys with invalid DataType: `{0}`."
    missing_keys_msg = ' Missing keys: "{0}".'

    def __init__(
        self,
        template: str,
        missing_keys: list[str] | None = None,
        invalid_types: dict[str, Any] | None = None,
    ):
        invalid_types_msg = ""
        if invalid_types:
            invalid_types_msg = self.invalid_types_msg.format(
                ", ".join(
                    [f'"{_key}" {str(_type)}' for _key, _type in invalid_types.items()]
                )
            )

        missing_keys_msg = ""
        if missing_keys:
            missing_keys_msg = self.missing_keys_msg.format(", ".join(missing_keys))
        super().__init__(self.msg.format(template, missing_keys_msg, invalid_types_msg))


class TemplateResult(str):
    """Result of template format with most of information in.

    Args:
        used_values (dict): Dictionary of template filling data with
            only used keys.
        solved (bool): For check if all required keys were filled.
        template (str): Original template.
        missing_keys (Iterable[str]): Missing keys that were not in the data.
            Include missing optional keys.
        invalid_types (dict): When key was found in data, but value had not
            allowed DataType. Allowed data types are `numbers`,
            `str`(`basestring`) and `dict`. Dictionary may cause invalid type
            when value of key in data is dictionary but template expect string
            of number.
    """

    used_values: dict[str, Any]
    solved: bool
    template: str
    missing_keys: list[str]
    invalid_types: dict[str, Any]

    def __new__(
        cls,
        filled_template: str,
        template: str,
        solved: bool,
        used_values: dict[str, Any],
        missing_keys: list[str],
        invalid_types: dict[str, Any],
    ) -> "TemplateResult":
        """Create a new TemplateResult instance.

        Args:
            filled_template (str): The filled template string.
            template (str): The original template string.
            solved (bool): Whether all required keys were filled.
            used_values (dict): Dictionary of template filling data with only used keys.
            missing_keys (list): List of missing keys that were not in the data.
            invalid_types (dict): Dictionary of keys with invalid data types.

        Returns:
            TemplateResult: A new instance of TemplateResult.
        """
        new_obj = super().__new__(cls, filled_template)
        new_obj.used_values = used_values
        new_obj.solved = solved
        new_obj.template = template
        new_obj.missing_keys = list(set(missing_keys))
        new_obj.invalid_types = invalid_types
        return new_obj

    def __copy__(self, *args, **kwargs) -> "TemplateResult":
        """Create a shallow copy of the TemplateResult instance.

        Returns:
            TemplateResult: A shallow copy of the instance.
        """
        return self.copy()

    def __deepcopy__(self, *args, **kwargs) -> "TemplateResult":
        """Create a deep copy of the TemplateResult instance.

        Returns:
            TemplateResult: A deep copy of the instance.
        """
        return self.copy()

    def validate(self) -> None:
        """Validate the TemplateResult instance.

        Raises:
            TemplateUnsolved: If the template is not fully solved.
        """
        if not self.solved:
            raise TemplateUnsolved(self.template, self.missing_keys, self.invalid_types)

    def copy(self) -> "TemplateResult":
        """Create a copy of the TemplateResult instance.

        Returns:
            TemplateResult: A copy of the instance.
        """
        cls = self.__class__
        return cls(
            str(self),
            self.template,
            self.solved,
            self.used_values,
            self.missing_keys,
            self.invalid_types,
        )

    def normalized(self) -> "TemplateResult":
        """Convert the template result to a normalized path.

        Returns:
            TemplateResult: A new instance with a normalized path.
        """
        cls = self.__class__
        return cls(
            os.path.normpath(self.replace("\\", "/")),
            self.template,
            self.solved,
            self.used_values,
            self.missing_keys,
            self.invalid_types,
        )


class TemplatePartResult:
    """Result to store result of template parts."""

    def __init__(self, optional: bool = False):
        # Missing keys or invalid value types of required keys
        self._missing_keys: set[str] = set()
        self._invalid_types: dict[str, type] = {}
        # Missing keys or invalid value types of optional keys
        self._missing_optional_keys: set[str] = set()
        self._invalid_optional_types: dict[str, type] = {}

        # Used values stored by key with origin type
        #   - key without any padding or key modifiers
        #   - value from filling data
        #   Example: {"version": 1}
        self._used_values: dict[str, Any] = {}
        # Used values stored by key with all modifiers
        #   - value is already formatted string
        #   Example: {"version:0>3": "001"}
        self._realy_used_values: dict[str, str] = {}
        # Concatenated string output after formatting
        self._output: str = ""
        # Is this result from optional part
        self._optional: bool = True

    def add_output(self, other: Union[str, "TemplatePartResult"]):
        if isinstance(other, str):
            self._output += other

        elif isinstance(other, TemplatePartResult):
            self._output += other.output

            self._missing_keys |= other.missing_keys
            self._missing_optional_keys |= other.missing_optional_keys

            self._invalid_types.update(other.invalid_types)
            self._invalid_optional_types.update(other.invalid_optional_types)

            if other.optional and not other.solved:
                return
            self._used_values.update(other.used_values)
            self._realy_used_values.update(other.realy_used_values)

        else:
            raise TypeError(
                f'Cannot add data from "{type(other)}"'
                f' to "{self.__class__.__name__}"'
            )

    @property
    def solved(self) -> bool:
        if self.optional:
            if (
                len(self.missing_optional_keys) > 0
                or len(self.invalid_optional_types) > 0
            ):
                return False
        return len(self.missing_keys) == 0 and len(self.invalid_types) == 0

    @property
    def optional(self) -> bool:
        return self._optional

    @property
    def output(self) -> str:
        return self._output

    @property
    def missing_keys(self) -> set[str]:
        return self._missing_keys

    @property
    def missing_optional_keys(self) -> set[str]:
        return self._missing_optional_keys

    @property
    def invalid_types(self) -> dict[str, type]:
        return self._invalid_types

    @property
    def invalid_optional_types(self) -> dict[str, type]:
        return self._invalid_optional_types

    @property
    def realy_used_values(self) -> dict[str, str]:
        return self._realy_used_values

    @property
    def used_values(self) -> dict[str, Any]:
        return self._used_values

    @staticmethod
    def split_keys_to_subdicts(values: dict[str, Any]) -> dict[str, Any]:
        output: dict[str, Any] = {}
        for key, value in values.items():
            if key_padding := list(KEY_PADDING_PATTERN.findall(key)):
                key = key_padding[0]
            key_subdict = list(SUB_DICT_PATTERN.findall(key))
            data = output
            last_key = key_subdict.pop(-1)
            for subkey in key_subdict:
                if subkey not in data:
                    data[subkey] = {}
                data = data[subkey]
            data[last_key] = value
        return output

    def get_clean_used_values(self) -> dict[str, Any]:
        new_used_values: dict[str, Any] = {}
        for key, value in self.used_values.items():
            if isinstance(value, FormatObject):
                value = str(value)
            new_used_values[key] = value

        return self.split_keys_to_subdicts(new_used_values)

    def add_realy_used_value(self, key: str, value: str):
        self._realy_used_values[key] = value

    def add_used_value(self, key: str, value: Any):
        self._used_values[key] = value

    def add_missing_key(self, key: str):
        if self._optional:
            self._missing_optional_keys.add(key)
        else:
            self._missing_keys.add(key)

    def add_invalid_type(self, key: str, value: Any):
        if self._optional:
            self._invalid_optional_types[key] = type(value)
        else:
            self._invalid_types[key] = type(value)


class FormatObject:
    """Object that can be used for formatting.

    This is base that is valid for to be used in 'StringTemplate' value.
    """

    def __init__(self):
        self.value = ""

    def __format__(self, *args, **kwargs) -> str:
        return self.value.__format__(*args, **kwargs)

    def __str__(self) -> str:
        return str(self.value)

    def __repr__(self) -> str:
        return self.__str__()


class FormattingPart:
    """String with formatting template.

    Containt only single key to format e.g. "{project[name]}".

    Args:
        template(str): String containing the formatting key.
    """

    def __init__(self, template: str):
        self._template = template

    @property
    def template(self) -> str:
        return self._template

    def __repr__(self) -> str:
        return f"<Format:{self._template}>"

    def __str__(self) -> str:
        return self._template

    @staticmethod
    def validate_value_type(value: Any) -> bool:
        """Check if value can be used for formatting of single key."""
        if isinstance(value, numbers.Number | FormatObject):
            return True

        for inh_class in type(value).mro():
            if inh_class is str:
                return True
        return False

    def format(self, data, result):
        """Format the formattings string.

        Args:
            data(dict): Data that should be used for formatting.
            result(TemplatePartResult): Object where result is stored.
        """
        key = self.template[1:-1]
        if key in result.realy_used_values:
            result.add_output(result.realy_used_values[key])
            return result

        # check if key expects subdictionary keys (e.g. project[name])
        existence_check = key
        if key_padding := list(KEY_PADDING_PATTERN.findall(existence_check)):
            existence_check = key_padding[0]
        key_subdict = list(SUB_DICT_PATTERN.findall(existence_check))

        value = data
        missing_key = False
        invalid_type = False
        used_keys = []
        for sub_key in key_subdict:
            if value is None or (hasattr(value, "items") and sub_key not in value):
                missing_key = True
                used_keys.append(sub_key)
                break

            if not hasattr(value, "items"):
                invalid_type = True
                break

            used_keys.append(sub_key)
            value = value.get(sub_key)

        if missing_key or invalid_type:
            if len(used_keys) == 0:
                invalid_key = key_subdict[0]
            else:
                invalid_key = used_keys[0]
                for idx, sub_key in enumerate(used_keys):
                    if idx == 0:
                        continue
                    invalid_key += f"[{sub_key}]"

            if missing_key:
                result.add_missing_key(invalid_key)

            elif invalid_type:
                result.add_invalid_type(invalid_key, value)

            result.add_output(self.template)
            return result

        if self.validate_value_type(value):
            fill_data = {}
            first_value = True
            for used_key in reversed(used_keys):
                if first_value:
                    first_value = False
                    fill_data[used_key] = value
                else:
                    _fill_data = {used_key: fill_data}
                    fill_data = _fill_data

            formatted_value = self.template.format(**fill_data)
            result.add_realy_used_value(key, formatted_value)
            result.add_used_value(existence_check, formatted_value)
            result.add_output(formatted_value)
            return result

        result.add_invalid_type(key, value)
        result.add_output(self.template)

        return result


class OptionalPart:
    """Template part which contains optional formatting strings.

    If this part can't be filled the result is empty string.

    Args:
        parts(list): Parts of template. Can contain 'str', 'OptionalPart' or
            'FormattingPart'.
    """

    def __init__(self, parts):
        self._parts = parts

    @property
    def parts(self):
        return self._parts

    def __str__(self):
        return f"<{''.join([str(p) for p in self._parts])}>"

    def __repr__(self):
        return f"<Optional:{''.join([str(p) for p in self._parts])}>"

    def format(self, data, result):
        new_result = TemplatePartResult(True)
        for part in self._parts:
            if isinstance(part, str):
                new_result.add_output(part)
            else:
                part.format(data, new_result)

        if new_result.solved:
            result.add_output(new_result)
        return result


class StringTemplate:
    """String that can be formatted."""

    def __init__(self, template):
        if not isinstance(template, str):
            raise TypeError(
                f"<{self.__class__.__name__}> argument must"
                f" be a string, not {type(template)}."
            )

        self._template = template
        parts: list[str | FormattingPart] = []
        last_end_idx = 0
        for item in KEY_PATTERN.finditer(template):
            start, end = item.span()
            if start > last_end_idx:
                parts.append(template[last_end_idx:start])
            parts.append(FormattingPart(template[start:end]))
            last_end_idx = end

        if last_end_idx < len(template):
            parts.append(template[last_end_idx:])

        new_parts: list[str | FormattingPart] = []
        for part in parts:
            if not isinstance(part, str):
                new_parts.append(part)
                continue

            substr = ""
            for char in part:
                if char not in ("<", ">"):
                    substr += char
                else:
                    if substr:
                        new_parts.append(substr)
                    new_parts.append(char)
                    substr = ""
            if substr:
                new_parts.append(substr)

        self._parts = self.find_optional_parts(new_parts)

    def __str__(self):
        return self.template

    def __repr__(self):
        return f"<{self.__class__.__name__}> {self.template}"

    def __contains__(self, other):
        return other in self.template

    def replace(self, *args, **kwargs):
        self._template = self.template.replace(*args, **kwargs)
        return self

    @property
    def template(self):
        return self._template

    def format(self, data):
        """Figure out with whole formatting.

        Separate advanced keys (*Like '{project[name]}') from string which must
        be formatted separatelly in case of missing or incomplete keys in data.

        Args:
            data (dict): Containing keys to be filled into template.

        Returns:
            TemplateResult: Filled or partially filled template containing all
                data needed or missing for filling template.
        """
        result = TemplatePartResult()
        for part in self._parts:
            if isinstance(part, str):
                result.add_output(part)
            else:
                part.format(data, result)

        invalid_types = result.invalid_types
        invalid_types.update(result.invalid_optional_types)
        invalid_types = result.split_keys_to_subdicts(invalid_types)

        missing_keys = result.missing_keys
        missing_keys |= result.missing_optional_keys

        solved = result.solved
        used_values = result.get_clean_used_values()

        return TemplateResult(
            result.output,
            self.template,
            solved,
            used_values,
            list(missing_keys),
            invalid_types,
        )

    def format_strict(self, *args, **kwargs):
        result = self.format(*args, **kwargs)
        result.validate()
        return result

    @classmethod
    def format_template(cls, template, data):
        objected_template = cls(template)
        return objected_template.format(data)

    @classmethod
    def format_strict_template(cls, template, data):
        objected_template = cls(template)
        return objected_template.format_strict(data)

    @staticmethod
    def find_optional_parts(parts):
        new_parts: list[Any] = []
        tmp_parts: dict[int, Any] = {}
        counted_symb = -1
        for part in parts:
            if part == "<":
                counted_symb += 1
                tmp_parts[counted_symb] = []

            elif part == ">":
                if counted_symb > -1:
                    parts = tmp_parts.pop(counted_symb)
                    counted_symb -= 1
                    # If part contains only single string keep value
                    #   unchanged
                    if parts:
                        # Remove optional start char
                        parts.pop(0)

                    value: str | OptionalPart

                    if not parts:
                        value = "<>"
                    elif len(parts) == 1 and isinstance(parts[0], str):
                        value = f"<{parts[0]}>"
                    else:
                        value = OptionalPart(parts)

                    if counted_symb < 0:
                        out_parts = new_parts
                    else:
                        out_parts = tmp_parts[counted_symb]
                    # Store value
                    out_parts.append(value)
                    continue

            if counted_symb < 0:
                new_parts.append(part)
            else:
                tmp_parts[counted_symb].append(part)

        if tmp_parts:
            for idx in sorted(tmp_parts.keys()):
                new_parts.extend(tmp_parts[idx])
        return new_parts
