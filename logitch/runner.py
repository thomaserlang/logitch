import click
import asyncio
from logitch import config, config_load, logger

@click.group()
@click.option('--config', default=None, help='path to the config file')
@click.option('--log_path', '-lp', default=None, help='a folder to store the log files in')
@click.option('--log_level', '-ll', default=None, help='notset, debug, info, warning, error or critical')
def cli(config, log_path, log_level):
    config_load(config)
    if log_path != None:
        config['logging']['path'] = log_path
    if log_level:
        config['logging']['level'] = log_level

@cli.command()
def twitch_log():
    logger.set_logger('twitch_log.log')

    loop = asyncio.get_event_loop()

    import logitch.irc
    loop.create_task(logitch.irc.main().connect())

    import logitch.pubsub
    loop.create_task(logitch.pubsub.main().run())

    loop.run_forever()

@cli.command()
def discord_log():
    logger.set_logger('discord_log.log')

    loop = asyncio.get_event_loop()

    import logitch.discord_log
    loop.create_task(logitch.discord_log.start())

    loop.run_forever()

@cli.command()
def web():
    logger.set_logger('web.log')
    import logitch.web
    logitch.web.main()

def main():
    cli()

if __name__ == "__main__":
    main()