# pylint: disable=line-too-long
"""Main module responsible for handling messages"""

import os
import openai
import asyncio
import discord
from src.log import logger
from random import randrange
from src.aclient import client
from discord import app_commands
from pymongo import MongoClient
from datetime import datetime


from src import log, art, personas, responses


def run_discord_bot():

    # Connect to MongoDB
    try:
        # Connect to MongoDB
        mongo_client = MongoClient('mongodb://host.docker.internal:27017')
        
        # Access the database
        db = mongo_client['ourgpt_development']

        # Access the collections
        preferences_collection = db['preferences']
        interactions_collection = db['interactions']
        
        user_preferences = preferences_collection.find_one({"username": "blueberry"})
        print(user_preferences)
        
    except Exception as e:
        print(f"An error occurred: {e}")

    @client.event
    async def on_ready():
        await client.send_start_prompt()
        await client.tree.sync()
        loop = asyncio.get_event_loop()
        loop.create_task(client.process_messages())
        logger.info(f'{client.user} is now running!')
    
    @client.tree.command(name="register", description="Register a new user with preferences")
    async def register(interaction: discord.Interaction, *, name: str, major: str, preference1: str, preference2: str):
        username = str(interaction.user)
        try:
            # Check if the user is already registered
            existing_user = preferences_collection.find_one({"username": username})

            if existing_user:
                await interaction.response.send_message("You are already registered.")
                return

            # Get the current date and time
            register_date = datetime.utcnow()

            # Data to be inserted
            data_to_insert = {
                "username": username,
                "major": major,
                "preferences": [preference1, preference2],
                "register_date": register_date
            }

            # Insert the data and check for errors
            insert_result = preferences_collection.insert_one(data_to_insert)
            if not insert_result.acknowledged:
                await interaction.response.send_message("Failed to register.")
                return

            # Confirm registration to the user
            await interaction.response.send_message(f"Successfully registered as {username}!")
        except Exception as e:
            await interaction.response.send_message(f"An error occurred: {str(e)}")

    @client.tree.command(name="delete", description="Delete yourself from the database")
    @app_commands.choices(confirm_deletion=[
        app_commands.Choice(name="Yes", value=1),
        app_commands.Choice(name="No", value=0),
    ])
    async def delete(interaction: discord.Interaction, confirm_deletion: app_commands.Choice[int]):
        await interaction.response.defer(ephemeral=False)

        username = str(interaction.user)

        # Check if the user is in the database
        existing_user = preferences_collection.find_one({"username": username})

        if not existing_user:
            await interaction.followup.send("You are not registered in the database.")
            return

        if confirm_deletion:
            # Delete the user from the database
            preferences_collection.delete_one({"username": username})

            # Confirm deletion to the user
            await interaction.followup.send("Your data has been deleted.")
        else:
            # Data has not been deleted
            await interaction.followup.send("Your data deletion has been cancelled.")

    @client.tree.command(name="list_users", description="See who is registered in the server")
    async def list_users(interaction: discord.Interaction):
        try:
            # Fetch all documents from the database collection
            all_users = preferences_collection.find({})

            # Initialize message
            message = "**Registered Users**\n```"

            # Add table headers
            message += f"{'Username':<20} | {'Register Date':<25}\n"
            message += "-" * 48 + "\n"

            # Add each user to the table
            for user in all_users:
                username = user.get("username", "N/A")
                register_date = user.get("register_date", "N/A")
                if isinstance(register_date, datetime):
                    register_date = register_date.strftime('%Y-%m-%d %H:%M:%S')

                message += f"{username:<20} | {register_date:<25}\n"

            # Close code block
            message += "```"

            # Send the message
            await interaction.response.send_message(message)
        except Exception as e:
            await interaction.response.send_message(f"An error occurred: {str(e)}")

    @client.tree.command(name='add_preferences', description='Add multiple preferences for a registered user')
    async def add_preferences(interaction: discord.Interaction, new_preferences: str):
        try:
            # Split the input string by spaces to get individual preferences
            preferences_list = new_preferences.split()

            # Fetch the username from the interaction (replace this based on your implementation)
            username = str(interaction.user)

            # Check if the user is already registered
            existing_user = preferences_collection.find_one({"username": username})

            if not existing_user:
                await interaction.response.send_message("You are not registered. Please register first.")
                return

            # Add the new preferences to the existing preferences
            update_result = preferences_collection.update_one(
                {"username": username},
                {"$addToSet": {"preferences": {"$each": preferences_list}}}
            )

            if update_result.modified_count == 0:
                await interaction.response.send_message("Preferences already exist or failed to update.")
                return

            # Confirm the addition to the user
            await interaction.response.send_message(f"Added new preferences: {', '.join(preferences_list)}")

        except Exception as e:
            await interaction.response.send_message(f"An error occurred: {str(e)}")
        
    @client.tree.command(name="chat", description="Have a chat with ChatGPT")
    async def chat(interaction: discord.Interaction, *, message: str):
        if client.is_replying_all == "True":
            await interaction.response.defer(ephemeral=False)
            await interaction.followup.send(
                "> **WARN: You already on replyAll mode. If you want to use the Slash Command, switch to normal mode by using `/replyall` again**")
            logger.warning("\x1b[31mYou already on replyAll mode, can't use slash command!\x1b[0m")
            return
        if interaction.user == client.user:
            return
        username = str(interaction.user)
        client.current_channel = interaction.channel
        logger.info(
            f"\x1b[31m{username}\x1b[0m : /chat [{message}] in ({client.current_channel})")

        # Parse preferences
        user_preferences = preferences_collection.find_one({"username": username})
        if user_preferences:
            preferences = user_preferences.get('preferences', [])
            name = username
            preferences_str = ", ".join(preferences)  # Convert list to string

            if preferences:
                condensed_preferences = f"These are my preferences: {preferences_str} I ask: {message}"
            else:
                condensed_preferences = message
        else:
            condensed_preferences = message
        
        # Store interaction
        interactions_collection.insert_one({"username": username, "interaction": message})
        await client.enqueue_message(interaction, condensed_preferences)


    @client.tree.command(name="private", description="Toggle private access")
    async def private(interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False)
        if not client.isPrivate:
            client.isPrivate = not client.isPrivate
            logger.warning("\x1b[31mSwitch to private mode\x1b[0m")
            await interaction.followup.send(
                "> **INFO: Next, the response will be sent via private reply. If you want to switch back to public mode, use `/public`**")
        else:
            logger.info("You already on private mode!")
            await interaction.followup.send(
                "> **WARN: You already on private mode. If you want to switch to public mode, use `/public`**")


    @client.tree.command(name="public", description="Toggle public access")
    async def public(interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False)
        if client.isPrivate:
            client.isPrivate = not client.isPrivate
            await interaction.followup.send(
                "> **INFO: Next, the response will be sent to the channel directly. If you want to switch back to private mode, use `/private`**")
            logger.warning("\x1b[31mSwitch to public mode\x1b[0m")
        else:
            await interaction.followup.send(
                "> **WARN: You already on public mode. If you want to switch to private mode, use `/private`**")
            logger.info("You already on public mode!")


    @client.tree.command(name="replyall", description="Toggle replyAll access")
    async def replyall(interaction: discord.Interaction):
        client.replying_all_discord_channel_id = str(interaction.channel_id)
        await interaction.response.defer(ephemeral=False)
        if client.is_replying_all == "True":
            client.is_replying_all = "False"
            await interaction.followup.send(
                "> **INFO: Next, the bot will response to the Slash Command. If you want to switch back to replyAll mode, use `/replyAll` again**")
            logger.warning("\x1b[31mSwitch to normal mode\x1b[0m")
        elif client.is_replying_all == "False":
            client.is_replying_all = "True"
            await interaction.followup.send(
                "> **INFO: Next, the bot will disable Slash Command and responding to all message in this channel only. If you want to switch back to normal mode, use `/replyAll` again**")
            logger.warning("\x1b[31mSwitch to replyAll mode\x1b[0m")


    @client.tree.command(name="chat-model", description="Switch different chat model")
    @app_commands.choices(choices=[
        app_commands.Choice(name="Official GPT-3.5", value="OFFICIAL"),
        app_commands.Choice(name="Ofiicial GPT-4.0", value="OFFICIAL-GPT4"),
        app_commands.Choice(name="Website ChatGPT-3.5", value="UNOFFICIAL"),
        app_commands.Choice(name="Website ChatGPT-4.0", value="UNOFFICIAL-GPT4"),
    ])

    async def chat_model(interaction: discord.Interaction, choices: app_commands.Choice[str]):
        await interaction.response.defer(ephemeral=False)
        original_chat_model = client.chat_model
        original_openAI_gpt_engine = client.openAI_gpt_engine

        try:
            if choices.value == "OFFICIAL":
                client.openAI_gpt_engine = "gpt-3.5-turbo"
                client.chat_model = "OFFICIAL"
            elif choices.value == "OFFICIAL-GPT4":
                client.openAI_gpt_engine = "gpt-4"
                client.chat_model = "OFFICIAL"
            elif choices.value == "UNOFFICIAL":
                client.openAI_gpt_engine = "gpt-3.5-turbo"
                client.chat_model = "UNOFFICIAL"
            elif choices.value == "UNOFFICIAL-GPT4":
                client.openAI_gpt_engine = "gpt-4"
                client.chat_model = "UNOFFICIAL"
            else:
                raise ValueError("Invalid choice")

            client.chatbot = client.get_chatbot_model()
            await interaction.followup.send(f"> **INFO: You are now in {client.chat_model} model.**\n")
            logger.warning(f"\x1b[31mSwitch to {client.chat_model} model\x1b[0m")

        except Exception as e:
            client.chat_model = original_chat_model
            client.openAI_gpt_engine = original_openAI_gpt_engine
            client.chatbot = client.get_chatbot_model()
            await interaction.followup.send(f"> **ERROR: Error while switching to the {choices.value} model, check that you've filled in the related fields in `.env`.**\n")
            logger.exception(f"Error while switching to the {choices.value} model: {e}")


    @client.tree.command(name="reset", description="Complete reset conversation history")
    async def reset(interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False)
        if client.chat_model == "OFFICIAL":
            client.chatbot = client.get_chatbot_model()
        elif client.chat_model == "UNOFFICIAL":
            client.chatbot.reset_chat()
            await client.send_start_prompt()
        await interaction.followup.send("> **INFO: I have forgotten everything.**")
        personas.current_persona = "standard"
        logger.warning(
            f"\x1b[31m{client.chat_model} bot has been successfully reset\x1b[0m")


    @client.tree.command(name="help", description="Show help for the bot")
    async def help(interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False)
        await interaction.followup.send(""":star: **BASIC COMMANDS** \n
        - `/chat [message]` Chat with ChatGPT!
        - `/draw [prompt]` Generate an image with the Dalle2 model
        - `/switchpersona [persona]` Switch between optional ChatGPT jailbreaks
                `random`: Picks a random persona
                `chatgpt`: Standard ChatGPT mode
                `dan`: Dan Mode 11.0, infamous Do Anything Now Mode
                `sda`: Superior DAN has even more freedom in DAN Mode
                `confidant`: Evil Confidant, evil trusted confidant
                `based`: BasedGPT v2, sexy GPT
                `oppo`: OPPO says exact opposite of what ChatGPT would say
                `dev`: Developer Mode, v2 Developer mode enabled

        - `/private` ChatGPT switch to private mode
        - `/public` ChatGPT switch to public mode
        - `/replyall` ChatGPT switch between replyAll mode and default mode
        - `/reset` Clear ChatGPT conversation history
        - `/register` Register yourself in the database for personalized messages
        - `/chat-model` Switch different chat model
                `OFFICIAL`: GPT-3.5 model
                `UNOFFICIAL`: Website ChatGPT
        - `/delete` Remove yourself from the database

For complete documentation, please visit:
https://github.com/jeffreyliuu/OurGPT""")

        logger.info(
            "\x1b[31mSomeone needs help!\x1b[0m")


    @client.tree.command(name="info", description="Bot information")
    async def info(interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False)
        chat_engine_status = client.openAI_gpt_engine
        chat_model_status = client.chat_model
        if client.chat_model == "UNOFFICIAL":
            chat_model_status = "ChatGPT(UNOFFICIAL)"
        elif client.chat_model == "OFFICIAL":
            chat_model_status = "OpenAI API(OFFICIAL)"
        if client.chat_model != "UNOFFICIAL" and client.chat_model != "OFFICIAL":
            chat_engine_status = "x"
        elif client.openAI_gpt_engine == "text-davinci-002-render-sha":
            chat_engine_status = "gpt-3.5"

        await interaction.followup.send(f"""
```fix
chat-model: {chat_model_status}
gpt-engine: {chat_engine_status}
```
""")


    @client.tree.command(name="draw", description="Generate an image with the Dalle2 model")
    @app_commands.choices(amount=[
        app_commands.Choice(name="1", value=1),
        app_commands.Choice(name="2", value=2),
        app_commands.Choice(name="3", value=3),
        app_commands.Choice(name="4", value=4),
        app_commands.Choice(name="5", value=5),
        app_commands.Choice(name="6", value=6),
        app_commands.Choice(name="7", value=7),
        app_commands.Choice(name="8", value=8),
        app_commands.Choice(name="9", value=9),
        app_commands.Choice(name="10", value=10),
    ])
    async def draw(interaction: discord.Interaction, *, prompt: str, amount: int = 1):
        if interaction.user == client.user:
            return

        username = str(interaction.user)
        channel = str(interaction.channel)
        logger.info(
            f"\x1b[31m{username}\x1b[0m : /draw [{prompt}] in ({channel})")

        await interaction.response.defer(thinking=True, ephemeral=client.isPrivate)
        try:
            path = await art.draw(prompt, amount)
            files = []
            for idx, img in enumerate(path):
                files.append(discord.File(img, filename=f"image{idx}.png"))
            title = f'> **{prompt}** - {str(interaction.user.mention)} \n\n'

            await interaction.followup.send(files=files, content=title)

        except openai.InvalidRequestError:
            await interaction.followup.send(
                "> **ERROR: Inappropriate request 😿**")
            logger.info(
            f"\x1b[31m{username}\x1b[0m made an inappropriate request.!")

        except Exception as e:
            await interaction.followup.send(
                "> **ERROR: Something went wrong 😿**")
            logger.exception(f"Error while generating image: {e}")


    @client.tree.command(name="switchpersona", description="Switch between optional chatGPT jailbreaks")
    @app_commands.choices(persona=[
        app_commands.Choice(name="Random", value="random"),
        app_commands.Choice(name="Standard", value="standard"),
        app_commands.Choice(name="Do Anything Now 11.0", value="dan"),
        app_commands.Choice(name="Superior Do Anything", value="sda"),
        app_commands.Choice(name="Evil Confidant", value="confidant"),
        app_commands.Choice(name="BasedGPT v2", value="based"),
        app_commands.Choice(name="OPPO", value="oppo"),
        app_commands.Choice(name="Developer Mode v2", value="dev"),
        app_commands.Choice(name="DUDE V3", value="dude_v3"),
        app_commands.Choice(name="AIM", value="aim"),
        app_commands.Choice(name="UCAR", value="ucar"),
        app_commands.Choice(name="Jailbreak", value="jailbreak")
    ])
    async def switchpersona(interaction: discord.Interaction, persona: app_commands.Choice[str]):
        if interaction.user == client.user:
            return

        await interaction.response.defer(thinking=True)
        username = str(interaction.user)
        channel = str(interaction.channel)
        logger.info(
            f"\x1b[31m{username}\x1b[0m : '/switchpersona [{persona.value}]' ({channel})")

        persona = persona.value

        if persona == personas.current_persona:
            await interaction.followup.send(f"> **WARN: Already set to `{persona}` persona**")

        elif persona == "standard":
            if client.chat_model == "OFFICIAL":
                client.chatbot.reset()
            elif client.chat_model == "UNOFFICIAL":
                client.chatbot.reset_chat()
            personas.current_persona = "standard"
            await interaction.followup.send(
                f"> **INFO: Switched to `{persona}` persona**")

        elif persona == "random":
            choices = list(personas.PERSONAS.keys())
            choice = randrange(0, 6)
            chosen_persona = choices[choice]
            personas.current_persona = chosen_persona
            await responses.switch_persona(chosen_persona, client)
            await interaction.followup.send(
                f"> **INFO: Switched to `{chosen_persona}` persona**")


        elif persona in personas.PERSONAS:
            try:
                await responses.switch_persona(persona, client)
                personas.current_persona = persona
                await interaction.followup.send(
                f"> **INFO: Switched to `{persona}` persona**")
            except Exception as e:
                await interaction.followup.send(
                    "> **ERROR: Something went wrong, please try again later! 😿**")
                logger.exception(f"Error while switching persona: {e}")

        else:
            await interaction.followup.send(
                f"> **ERROR: No available persona: `{persona}` 😿**")
            logger.info(
                f'{username} requested an unavailable persona: `{persona}`')


    @client.event
    async def on_message(message):
        if client.is_replying_all == "True":
            if message.author == client.user:
                return
            if client.replying_all_discord_channel_id:
                if message.channel.id == int(client.replying_all_discord_channel_id):
                    username = str(message.author)
                    user_message = str(message.content)
                    client.current_channel = message.channel
                    logger.info(f"\x1b[31m{username}\x1b[0m : '{user_message}' ({client.current_channel})")

                    await client.enqueue_message(message, user_message)
            else:
                logger.exception("replying_all_discord_channel_id not found, please use the command `/replyall` again.")

    TOKEN = os.getenv("DISCORD_BOT_TOKEN")

    client.run(TOKEN)