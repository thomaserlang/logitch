import click
import asyncio
from logitch import config, config_load, logger

@click.command()
@click.option('--config', default=None, help='path to the config file')
@click.option('--log_path', '-lp', default=None, help='a folder to store the log files in')
@click.option('--log_level', '-ll', default=None, help='notset, debug, info, warning, error or critical')
def cli(config, log_path, log_level):
    config_load(config)
    if log_path != None:
        config['logging']['path'] = log_path
    if log_level:
        config['logging']['level'] = log_level

    logger.set_logger('logitch.log')

    loop = asyncio.get_event_loop()

    import logitch.irc
    loop.create_task(logitch.irc.main().connect())

    import logitch.pubsub
    loop.create_task(logitch.pubsub.main().run())

    loop.run_forever()

def main():
    cli()

if __name__ == "__main__":
    main()