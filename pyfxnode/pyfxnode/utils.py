import json
from datetime import datetime
from typing import Union, Any

import msgpack
import pytz
from dateutil import parser

JST = pytz.timezone('Asia/Tokyo')


def utc_now_aware() -> datetime:
    """return utc_now aware"""
    return pytz.utc.localize(datetime.utcnow())


def jst_now_aware() -> datetime:
    """return jst_now aware"""
    return utc_now_aware().astimezone(JST)


def parse_datetime(dt: Union[str, datetime]) -> datetime:
    if isinstance(dt, str):
        dt = parser.parse(dt)
    assert isinstance(dt, datetime), 'dt is {}, must be (str, datetime)'.format(dt)
    if not dt.tzinfo:
        dt = pytz.utc.localize(dt)
    return dt


def datetime_str(dt: datetime) -> str:
    if dt.tzinfo:
        dt = dt.astimezone(pytz.utc)
    else:
        dt = pytz.utc.localize(dt)
    return dt.strftime('%Y-%m-%dT%H:%M:%S.%fZ')


class NamedTupleMixin:
    @classmethod
    def _get_defaults(cls) -> dict:
        return {}

    def __new__(cls, *args, **kwargs):
        fields = getattr(cls, '_fields')
        new_kwargs = dict(tuple(zip(fields, args)))
        new_kwargs.update(**kwargs)

        for k, (default, converter) in cls._get_defaults().items():
            if k not in new_kwargs:
                if default is not None:
                    if callable(default):
                        default = default()
                    new_kwargs[k] = default
            else:
                if converter is not None:
                    new_kwargs[k] = converter(new_kwargs[k])

        return getattr(super(), '__new__')(cls, **new_kwargs)

    def replace(self, **kwargs):
        return getattr(self, '_replace')(**kwargs)

    def to_dict(self) -> dict:
        return dict(**getattr(self, '_asdict')())

    @classmethod
    def from_dict(cls, d: dict):
        return cls(**d)

    def to_json(self) -> str:
        return to_json(self.to_dict())

    @classmethod
    def from_json(cls, json_text: str):
        return cls.from_dict(json.loads(json_text))


def to_json(obj: Any) -> str:
    """support datetime"""

    def default(o):
        if isinstance(o, datetime):
            if o.tzinfo is None:
                o = pytz.utc.localize(o)
            o = o.astimezone(pytz.utc)
            return o.strftime('%Y-%m-%dT%H:%M:%S.%fZ')
        raise TypeError('Object {} is not JSON serializable'.format(repr(o)))

    return json.dumps(obj, default=default)


# msgpack

def _msgpack_encode(obj: Any):
    if isinstance(obj, datetime):
        return {'__datetime__': True, 'data': datetime_str(obj)}
    return obj


def _msgpack_decode(obj: dict):
    if '__datetime__' in obj:
        return parse_datetime(obj['data'])
    return obj


def get_packer():
    return msgpack.Packer(default=_msgpack_encode, use_bin_type=True)


def get_unpacker():
    return msgpack.Unpacker(encoding='utf-8', object_hook=_msgpack_decode)


def pack_to_bytes(obj: Any) -> bytes:
    return msgpack.packb(obj, default=_msgpack_encode, use_bin_type=True)


def unpack_from_bytes(data: bytes) -> Any:
    return msgpack.unpackb(data, encoding='utf-8', object_hook=_msgpack_decode)
