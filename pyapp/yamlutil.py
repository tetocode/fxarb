from collections import defaultdict

import yaml
from yaml.representer import SafeRepresenter
from yaml.resolver import BaseResolver


def recursive_defaultdict(**kwargs):
    dd = defaultdict(recursive_defaultdict)
    dd.update(kwargs)
    return dd


def init_yaml():

    yaml.add_constructor(BaseResolver.DEFAULT_MAPPING_TAG,
                         lambda loader, node: recursive_defaultdict(**dict(loader.construct_pairs(node))))
    yaml.add_representer(defaultdict, SafeRepresenter.represent_dict)


def dumps_yaml(obj, flow_style=False) -> str:
    return yaml.dump(obj, default_flow_style=flow_style)


def load_yaml(file_name, default=None) -> dict:
    try:
        with open(file_name, 'r') as f:
            return yaml.load(f)
    except FileNotFoundError:
        return default


def save_yaml(obj, file_name) -> bool:
    try:
        with open(file_name, 'w') as f:
            f.write(dumps_yaml(obj))
        return True
    except IOError:
        return False
