"""Main handler for the Discord ChatGPT bot"""
import sys
import pkg_resources
from dotenv import load_dotenv
from src import bot
from src import log



def check_version() -> None:
    """ Function that ensures each requirement has the correct package installed
    """

    load_dotenv()
    logger = log.setup_logger(__name__)

    # Read the requirements.txt file and add each line to a list
    with open('requirements.txt', encoding='utf-8') as file:
        required = file.read().splitlines()

    # For each library listed in requirements.txt, check if the corresponding version is installed
    for package in required:
        # Use the pkg_resources library to get information about the installed version of library
        package_name, package_version = package.split('==')
        installed = pkg_resources.get_distribution(package_name)
        # Extract the library name and version number
        name, version = installed.project_name, installed.version
        # Compare the version number to see if it matches the one in requirements.txt
        if package != f'{name}=={version}':
            logger.error('%s ver. %s  but is not matching requirements', name, version)
            sys.exit()

if __name__ == '__main__':
    print(sys.path)
    check_version()
    bot.run_discord_bot()
