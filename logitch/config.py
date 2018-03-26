import os, yaml

config = {
    'irc': {
        'username': '',
        'password': '',
        'host': '',
        'port': 6667,
        'use_ssl': False,
        'channels': [],
        'sql_url': '',
    },    
    'logging': {
        'level': 'warning',
        'path': None,
        'max_size': 100 * 1000 * 1000,# ~ 95 mb
        'num_backups': 10,
    },
}

def load(path=None):
    default_paths = [
        '~/logitch.yaml',
        './logitch.yaml',
        '/etc/logitch/logitch.yaml',
        '/etc/logitch.yaml',
    ]
    if not path:
        path = os.environ.get('LOGITCH_CONFIG', None)
        if not path:
            for p in default_paths:
                p = os.path.expanduser(p)
                if os.path.isfile(p):
                    path = p
                    break
    if not path:
        raise Exception('No config file specified.')
    if not os.path.isfile(path):
        raise Exception('Config: "{}" could not be found.'.format(path))
    with open(path) as f:
        data = yaml.load(f)
    for key in data:
        if key in config:
            if isinstance(config[key], dict):
                config[key].update(data[key])
            else:
                config[key] = data[key]