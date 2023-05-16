# pylint: disable=line-too-long
"""Main module responsible for handling messages"""

import os
import openai
from discord import app_commands
import discord
from pymongo import MongoClient
from src import responses, log, art, personas
logger = log.setup_logger(__name__)

IS_PRIVATE = False

client = MongoClient("<your_mongodb_connection_string>")
db = client["user_database"]
users_collection = db["users"]

class AClient(discord.Client):
    """Handler for the overall discord bot

    Args:
        discord (client): Discord client
    """
    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.activity = discord.Activity(type=discord.ActivityType.listening, name="/chat | /help")

async def send_message(message, user_message):
    """_summary_

    Args:
        message: object that contains the received message
        user_message: object that contains the sent message
    """
    is_reply_all = os.getenv("REPLYING_ALL")
    if is_reply_all == "False":
        author = message.user.id
        await message.response.defer(ephemeral=IS_PRIVATE)
    else:
        author = message.author.id
    try:
        user = users_collection.find_one({"user_id": author})
        if user:
            # Retrieve user information from MongoDB and use it to personalize the response
            user_name = user["name"]
            user_friends = user.get("friends", [])
            user_school = user.get("school", "")
            user_preferences = user.get("preferences", {})
            
            # Use retrieved user information to personalize the response
            response = f'> **{user_message}** - <@{str(author)}' + f'> \n\nHello {user_name}, '
            response += f"You have {len(user_friends)} friends, your school is {user_school}, "
            response += f"and your preferences are {user_preferences}."
        else:
            response = f'> **{user_message}** - <@{str(author)}' + '> \n\n'
        chat_model = os.getenv("CHAT_MODEL")
        
    
    # Add the user's question to the end of the prompt
        if chat_model == "OFFICIAL":
            response = f"{response}{await responses.official_handle_response(user_message)}"
        elif chat_model == "UNOFFICIAL":
            response = f"{response}{await responses.unofficial_handle_response(user_message)}"
        char_limit = 1900
        if len(response) > char_limit:
            # Split the response into smaller chunks of no more than 1900 characters each(Discord limit is 2000 per chunk)
            if "```" in response:
                # Split the response if the code block exists
                parts = response.split("```")

                for i, part in enumerate(parts):
                    if i%2 == 0: # indices that are even are not code blocks
                        if is_reply_all == "True":
                            await message.channel.send(part)
                        else:
                            await message.followup.send(part)

                    else: # Odd-numbered parts are code blocks
                        code_block = part.split("\n")
                        formatted_code_block = ""
                        for line in code_block:
                            while len(line) > char_limit:
                                # Split the line at the 50th character
                                formatted_code_block += line[:char_limit] + "\n"
                                line = line[char_limit:]
                            formatted_code_block += line + "\n"  # Add the line and seperate with new line

                        # Send the code block in a separate message
                        if len(formatted_code_block) > char_limit+100:
                            code_block_chunks = [formatted_code_block[i:i+char_limit]
                                                 for i in range(0, len(formatted_code_block), char_limit)]
                            for chunk in code_block_chunks:
                                if is_reply_all == "True":
                                    await message.channel.send(f"```{chunk}```")
                                else:
                                    await message.followup.send(f"```{chunk}```")
                        elif is_reply_all == "True":
                            await message.channel.send(f"```{formatted_code_block}```")
                        else:
                            await message.followup.send(f"```{formatted_code_block}```")

            else:
                response_chunks = [response[i:i+char_limit]
                                   for i in range(0, len(response), char_limit)]
                for chunk in response_chunks:
                    if is_reply_all == "True":
                        await message.channel.send(chunk)
                    else:
                        await message.followup.send(chunk)
        elif is_reply_all == "True":
            await message.channel.send(response)
        else:
            await message.followup.send(response)
    except Exception as err:
        if is_reply_all == "True":
            await message.channel.send("> **Error: Something went wrong, please try again later!**")
        else:
            await message.followup.send("> **Error: Something went wrong, please try again later!**")
        logger.exception("Error while sending message: %s", err)


async def send_start_prompt(client):
    """ Method that sens starting prompt to the channel

    Args:
        client : discord client object
    """

    config_dir = os.path.abspath(f"{__file__}/../../")
    prompt_name = 'starting-prompt.txt'
    prompt_path = os.path.join(config_dir, prompt_name)
    discord_channel_id = os.getenv("DISCORD_CHANNEL_ID")
    try:
        if os.path.isfile(prompt_path) and os.path.getsize(prompt_path) > 0:
            with open(prompt_path, "r", encoding="utf-8") as file:
                prompt = file.read()
                if discord_channel_id:
                    logger.info('Send starting prompt with size %i', len(prompt))
                    chat_model = os.getenv("CHAT_MODEL")
                    response = ""
                    if chat_model == "OFFICIAL":
                        response = f"{response}{await responses.official_handle_response(prompt)}"
                    elif chat_model == "UNOFFICIAL":
                        response = f"{response}{await responses.unofficial_handle_response(prompt)}"
                    await client.wait_until_ready()
                    channel = client.get_channel(int(discord_channel_id))
                    await channel.send(response)
                    logger.info('Starting prompt response: %s', response)
                else:
                    logger.info("No Channel selected. Skip sending starting prompt.")
        else:
            logger.info('No %s. Skip sending starting prompt.', prompt_name)
    except Exception as err:
        logger.exception('Error while sending starting prompt: %s', err)


def run_discord_bot():
    """
    Class that contains methods to run the bot
    """
    client = AClient()

    @client.event
    async def on_ready():
        await send_start_prompt(client)
        await client.tree.sync()
        logger.info('%s is now running!', client.user)


    @client.tree.command(name="chat", description="Have a chat with ChatGPT")
    async def chat(interaction: discord.Interaction, *, message: str):
        is_reply_all =  os.getenv("REPLYING_ALL")
        if is_reply_all == "True":
            await interaction.response.defer(ephemeral=False)
            await interaction.followup.send(
                "> **Warn: You already on replyAll mode. If you want to use slash command, switch to normal mode, use `/replyall` again**")
            logger.warning("\x1b[31mYou already on replyAll mode, can't use slash command!\x1b[0m")
            return
        if interaction.user == client.user:
            return
        username = str(interaction.user)
        channel = str(interaction.channel)
        logger.info(
            '\x1b[31m%s\x1b[0m : /chat [%s] in (%s)', username, message, channel)
        await send_message(interaction, message)


    @client.tree.command(name="private", description="Toggle private access")
    async def private(interaction: discord.Interaction):
        global IS_PRIVATE
        await interaction.response.defer(ephemeral=False)
        if not IS_PRIVATE:
            IS_PRIVATE = not IS_PRIVATE
            logger.warning("\x1b[31mSwitch to private mode\x1b[0m")
            await interaction.followup.send(
                "> **Info: Next, the response will be sent via private message. If you want to switch back to public mode, use `/public`**")
        else:
            logger.info("You already on private mode!")
            await interaction.followup.send(
                "> **Warn: You already on private mode. If you want to switch to public mode, use `/public`**")


    @client.tree.command(name="public", description="Toggle public access")
    async def public(interaction: discord.Interaction):
        global IS_PRIVATE
        await interaction.response.defer(ephemeral=False)
        if IS_PRIVATE:
            IS_PRIVATE = not IS_PRIVATE
            await interaction.followup.send(
                "> **Info: Next, the response will be sent to the channel directly. If you want to switch back to private mode, use `/private`**")
            logger.warning("\x1b[31mSwitch to public mode\x1b[0m")
        else:
            await interaction.followup.send(
                "> **Warn: You already on public mode. If you want to switch to private mode, use `/private`**")
            logger.info("You already on public mode!")


    @client.tree.command(name="replyall", description="Toggle replyAll access")
    async def replyall(interaction: discord.Interaction):
        is_reply_all = os.getenv("REPLYING_ALL")
        os.environ["REPLYING_ALL_DISCORD_CHANNEL_ID"] = str(interaction.channel_id)
        await interaction.response.defer(ephemeral=False)
        if is_reply_all == "True":
            os.environ["REPLYING_ALL"] = "False"
            await interaction.followup.send(
                "> **Info: The bot will only response to the slash command `/chat` next. If you want to switch back to replyAll mode, use `/replyAll` again.**")
            logger.warning("\x1b[31mSwitch to normal mode\x1b[0m")
        elif is_reply_all == "False":
            os.environ["REPLYING_ALL"] = "True"
            await interaction.followup.send(
                "> **Info: Next, the bot will response to all message in this channel only.If you want to switch back to normal mode, use `/replyAll` again.**")
            logger.warning("\x1b[31mSwitch to replyAll mode\x1b[0m")


    @client.tree.command(name="chat-model", description="Switch different chat model")
    @app_commands.choices(choices=[
        app_commands.Choice(name="Official GPT-3.5", value="OFFICIAL"),
        app_commands.Choice(name="Website ChatGPT", value="UNOFFICIAL")
    ])
    async def chat_model(interaction: discord.Interaction, choices: app_commands.Choice[str]):
        await interaction.response.defer(ephemeral=False)
        if choices.value == "OFFICIAL":
            responses.chatbot = responses.get_chatbot_model("OFFICIAL")
            os.environ["CHAT_MODEL"] = "OFFICIAL"
            await interaction.followup.send(
                "> **Info: You are now in Official GPT-3.5 model.**\n> You need to set your `OPENAI_API_KEY` in `env` file.")
            logger.warning("\x1b[31mSwitch to OFFICIAL chat model\x1b[0m")
        elif choices.value == "UNOFFICIAL":
            responses.chatbot = responses.get_chatbot_model("UNOFFICIAL")
            os.environ["CHAT_MODEL"] = "UNOFFICIAL"
            await interaction.followup.send(
                "> **Info: You are now in Website ChatGPT model.**\n> You need to set your `SESSION_TOKEN` or `OPENAI_EMAIL` and `OPENAI_PASSWORD` in `env` file.")
            logger.warning("\x1b[31mSwitch to UNOFFICIAL(Website) chat model\x1b[0m")


    @client.tree.command(name="reset", description="Complete reset ChatGPT conversation history")
    async def reset(interaction: discord.Interaction):
        chat_model = os.getenv("CHAT_MODEL")
        if chat_model == "OFFICIAL":
            responses.chatbot.reset()
        elif chat_model == "UNOFFICIAL":
            responses.chatbot.reset_chat()
        await interaction.response.defer(ephemeral=False)
        await interaction.followup.send("> **Info: I have forgotten everything.**")
        # personas.current_persona = "standard"
        logger.warning(
            "\x1b[31mChatGPT bot has been successfully reset\x1b[0m")
        await send_start_prompt(client)


    @client.tree.command(name="help", description="Show help for the bot")
    async def help(interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False)
        await interaction.followup.send(""":star:**BASIC COMMANDS** \n
        - `/chat [message]` Chat with ChatGPT!
        - `/private` ChatGPT switch to private mode
        - `/public` ChatGPT switch to public mode
        - `/replyall` ChatGPT switch between replyAll mode and default mode
        - `/reset` Clear ChatGPT conversation history
        - `/chat-model` Switch different chat model
                `OFFICIAL`: GPT-3.5 model
                `UNOFFICIAL`: Website ChatGPT
                Modifying CHAT_MODEL field in the .env file change the default model
        For complete documentation, please visit <insert github linke here>""")

        logger.info(
            "\x1b[31mSomeone needs help!\x1b[0m")

    @client.tree.command(name="draw", description="Generate an image with the Dalle2 model")
    async def draw(interaction: discord.Interaction, *, prompt: str):
        is_reply_all =  os.getenv("REPLYING_ALL")
        if is_reply_all == "True":
            await interaction.response.defer(ephemeral=False)
            await interaction.followup.send(
                "> **Warn: You already on replyAll mode. If you want to use slash command, switch to normal mode, use `/replyall` again**")
            logger.warning("\x1b[31mYou already on replyAll mode, can't use slash command!\x1b[0m")
            return
        if interaction.user == client.user:
            return

        #await interaction.response.defer(ephemeral=False)
        username = str(interaction.user)
        channel = str(interaction.channel)
        logger.info(
            f"\x1b[31m{username}\x1b[0m : /draw [{prompt}] in ({channel})")


        await interaction.response.defer(thinking=True)
        try:
            path = await art.draw(prompt)

            file = discord.File(path, filename="image.png")
            title = '> **' + prompt + '**\n'
            embed = discord.Embed(title=title)
            embed.set_image(url="attachment://image.png")

            # send image in an embed
            await interaction.followup.send(file=file, embed=embed)

        except openai.InvalidRequestError:
            await interaction.followup.send(
                "> **Warn: Inappropriate request 😿**")
            logger.info(
            '\x1b[31m%s\x1b[0m made an inappropriate request.!', username)

        except Exception as err:
            await interaction.followup.send(
                "> **Warn: Something went wrong 😿**")
            logger.exception('Error while generating image: %s', err)


    @client.tree.command(name="switchmode", description="Switch between optional chatGPT personalities")
    @app_commands.choices(persona=[
        app_commands.Choice(name="Standard", value="standard"),
        app_commands.Choice(name="Do Anything Now 11.0", value="dan"),
        app_commands.Choice(name="Superior Do Anything", value="sda"),
        app_commands.Choice(name="Evil Confidant", value="confidant"),
        app_commands.Choice(name="BasedGPT v2", value="based"),
        app_commands.Choice(name="OPPO", value="oppo"),
        app_commands.Choice(name="Developer Mode v2", value="dev")
    ])
    async def chat(interaction: discord.Interaction, persona: app_commands.Choice[str]):
        is_reply_all =  os.getenv("REPLYING_ALL")
        if is_reply_all == "True":
            await interaction.response.defer(ephemeral=False)
            await interaction.followup.send(
                "> **Warn: You already on replyAll mode. If you want to use slash command, switch to normal mode, use `/replyall` again**")
            logger.warning("\x1b[31mYou already on replyAll mode, can't use slash command!\x1b[0m")
            return
        if interaction.user == client.user:
            return

        await interaction.response.defer(thinking=True)
        username = str(interaction.user)
        channel = str(interaction.channel)
        logger.info(
            "\x1b[31m%sx1b[0m : '/switchpersona [%s]' (%s)", username, persona.value, channel)

        persona = persona.value

        if persona == personas.current_persona:
            await interaction.followup.send(f"> **Warn: Already set to `{persona}` persona**")

        elif persona == "standard":
            chat_model = os.getenv("CHAT_MODEL")
            if chat_model == "OFFICIAL":
                responses.chatbot.reset()
            elif chat_model == "UNOFFICIAL":
                responses.chatbot.reset_chat()

            personas.current_persona = "standard"
            await interaction.followup.send(
                f"> **Info: Switched to `{persona}` persona**")

        elif persona in personas.PERSONAS:
            try:
                await responses.switch_persona(persona)
                personas.current_persona = persona
                await interaction.followup.send(
                f"> **Info: Switched to `{persona}` persona**")
            except Exception as err:
                await interaction.followup.send(
                    "> **Error: Something went wrong, please try again later! 😿**")
                logger.exception('Error while switching persona: %s', err)

        else:
            await interaction.followup.send(
                f"> **Error: No available persona: `{persona}` 😿**")
            logger.info(
                f'{username} requested an unavailable persona: `{persona}`')

    @client.event
    async def on_message(message):
        is_reply_all =  os.getenv("REPLYING_ALL")
        if is_reply_all == "True" and message.channel.id == int(os.getenv("REPLYING_ALL_DISCORD_CHANNEL_ID")):
            if message.author == client.user:
                return
            username = str(message.author)
            user_message = str(message.content)
            channel = str(message.channel)
            logger.info('\x1b[31m%s\x1b[0m : %s (%s)', username, user_message, channel)
            await send_message(message, user_message)

    token = os.getenv("DISCORD_BOT_TOKEN")

    client.run(token)
