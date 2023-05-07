import discord
from discord import app_commands
from discord.ext import commands, tasks
from discord.ui import View
from datetime import datetime, time
from dateutil.tz import gettz
from typing import Optional
import asyncpg
import os
import postgres
import utils
import openai
import random
import asyncio
from dotenv import load_dotenv

# Read .env
load_dotenv()

# Get question from ChatGpt
def get_question(*args, **kwargs) -> str:
    openai.api_key = (str)(os.getenv('OPENAI_API_KEY'))
    success: bool = False
    delay: float = 1
    exponential_base: float = 2
    jitter: bool = True
    num_retries: int = 0
    max_retries: int = 10
    prompt: str = f'Give me a conversation starter question'
    while not success:
        try:
            response = openai.ChatCompletion.create(
                model='gpt-3.5-turbo',
                messages=[{
                    'role': 'assistant',
                    'content': prompt,
                    'name': 'qotd-bot'
                }],
                temperature=1.0,
                max_tokens=200,
                top_p=1,
                frequency_penalty=1.5,
                presence_penalty=1.5
            )
            print(response)
        except openai.APIError as e:
            num_retries += 1
            if num_retries > max_retries:
                return ('Request timed out. Please try again.')
            delay *= exponential_base * (1 + jitter * random.random())
            asyncio.sleep(delay)
        except openai.InvalidRequestError as e:
            continue
        except Exception as e:
            continue
        else:
            success = True
            question: str = response.choices[0]['message']['content'].strip('\"')
            invalid_responses: list = [
                "I'm sorry, I cannot generate inappropriate or offensive content.", "AI language model",]
            for invalid in invalid_responses:
                if invalid in question:
                    success = False
                    break
            if success:
                return question
    return None


class PendingQOTDView(View):
    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=None)
        self.bot = bot
    
    @discord.ui.button(label='Approve', style=discord.ButtonStyle.green, emoji='👍')
    async def approve_button_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Get qotd channel
        try:
            query: str = '''
                SELECT qotd_channel_id
                FROM guilds
                WHERE guild_id = $1
            '''
            response = await self.bot.db.fetchrow(query, interaction.guild_id)
        except asyncpg.PostgresError as e:
            await postgres.send_postgres_error_embed(bot=self.bot, query=query, error_msg=e)
        
        if response:
            qotd_channel: discord.abc.GuildChannel = self.bot.get_channel(response.get('qotd_channel_id'))

            # Edit original embed to show "Approved" under status
            if interaction.message.embeds[0]: # Edit field if embed exists
                updated_pending_qotd_embed: discord.Embed = interaction.message.embeds[0].set_field_at( 
                    index=1,
                    name='Status',
                    value='Approved ✅',
                    inline=False
                )
                await interaction.response.edit_message(embed=updated_pending_qotd_embed, view=None) # Disable buttons from pending message

            # Create qotd embed
            qotd_embed: discord.Embed = discord.Embed(
                title=f'<:question:956191743743762453><:grey_question:956191743743762453>'
                    f'Question of The Day<:grey_question:956191743743762453><:question:956191743743762453>',
                description=f'{interaction.message.embeds[0].fields[0].value}', 
                color=0xFC94AF,
                timestamp=datetime.now()
            )
            qotd_message: discord.Message = await qotd_channel.send(embed=qotd_embed)
            

    @discord.ui.button(label='Reroll', style=discord.ButtonStyle.red, emoji='🔁')
    async def callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        question: str = None
        while True:
            question: str = get_question()
            if question:
                break

        old_embed: discord.Embed = interaction.message.embeds[0]
        if old_embed:
            new_embed: discord.Embed = old_embed.set_field_at(
                index=0,
                name='Question',
                value=question,
                inline=False
            ) 
            await interaction.response.edit_message(embed=new_embed)


class Qotd(commands.Cog):
    '''Question of The Day Cog'''
    OWNER_GUILD_ID = os.getenv('OWNER_GUILD_ID')

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.bot.tree.on_error = self.cog_app_command_error # Add error handler to bot tree
        

    async def cog_load(self) -> None:
        self.qotd_send_question.start() # Start task
        print('* QOTD module READY')


    async def cog_unload(self) -> None:
        '''Gracefully stops all tasks from running'''
        self.qotd_send_question.stop()


    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
        '''Error handler for QOTD module'''
        to_send: str = '[ERROR]: '
        if isinstance(error, app_commands.MissingPermissions):
            to_send += f'You are missing `{error.missing_permissions}` permission(s) to use this command in this channel.'
        elif isinstance(error, app_commands.BotMissingPermissions):
            to_send += f'I am missing `{error.missing_permissions}` permission(s) to use this command in this channel.'
        elif isinstance(error, discord.NotFound):
            to_send += f'Could not find channel.\n\n{error}'
        elif isinstance(error, discord.Forbidden):
            to_send += f'{error}'
        else:
            to_send += f'{error}'

        if not interaction.response.is_done():
            await interaction.response.send_message(to_send, ephemeral=True)        


    # Set up QOTD
    @app_commands.command(name='setup', description='Set up QOTD')
    @app_commands.checks.has_permissions(manage_guild=True, manage_channels=True)
    @app_commands.checks.bot_has_permissions(manage_channels=True)
    async def qotd_setup(
        self, 
        interaction: discord.Interaction, 
        channel: Optional[discord.TextChannel]
    ) -> None:
        """Setup command for QOTD module."""
        interaction_msg: str = ''
        # Check if server requires QOTD setup
        try:
            query: str = '''
                SELECT qotd_channel_id, qotd_approval_channel_id
                FROM guilds 
                WHERE guild_id = $1
                '''
            response = await self.bot.db.fetch(query, interaction.guild_id)
        except asyncpg.PostgresError as e:
            await postgres.send_postgres_error_embed(bot=self.bot, query=query, error_msg=e)
        else:
            if not response:
                await interaction.response.send_message('**[ERROR]:** Could not set up QOTD. Please try again later.', ephemeral=True)

        # Set given channel as QOTD channel if given, else create QOTD channel
        qotd_channel: discord.abc.GuildChannel = interaction.guild.get_channel(response[0].get('qotd_channel_id'))
        qotd_approval_channel: discord.abc.GuildChannel = interaction.guild.get_channel(response[0].get('qotd_approval_channel_id'))
        if qotd_channel and qotd_approval_channel:
            interaction_msg += f'QOTD is already set up in {qotd_channel.mention}. If you want to edit channels, please use `/qotd channel`.'
        else:
            # Check if channel given is a text channel
            if channel and isinstance(channel, discord.TextChannel):
                required_command_perms: list[tuple] = {
                    ('read_messages', True), ('send_messages', True), 
                    ('embed_links', True), ('read_message_history', True)
                }
                missing_perms: list = utils.perms_check(interaction.guild.get_member(self.bot.user.id), channel, required_command_perms)
                if missing_perms:
                    interaction_msg += f'Bot is missing these required permissions `{missing_perms}` in {channel.mention} for QOTD.'
                else:
                    qotd_channel = channel
            # Create QOTD channel if no channel or incorrect channel given
            else:
                overwrites = {
                    interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
                    interaction.guild.me: discord.PermissionOverwrite( # Necessary permissions for bot
                        read_messages=True,
                        send_messages=True,
                        embed_links=True,
                        read_message_history=True,
                    )
                }
                qotd_channel: discord.abc.GuildChannel = await interaction.guild.create_text_channel(name='qotd', reason='QOTD setup', overwrites=overwrites)
                if qotd_channel:
                    interaction_msg += f'Successfully set up QOTD.\nQuestions will appear in {qotd_channel.mention}.'

            # Create approval channel if it does not exist
            if not qotd_approval_channel:
                overwrites = {
                    interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
                    interaction.guild.me: discord.PermissionOverwrite( # Necessary permissions for bot
                        read_messages=True,
                        send_messages=True,
                        embed_links=True,
                        read_message_history=True,
                    )
                }
                qotd_approval_channel: discord.abc.GuildChannel = await interaction.guild.create_text_channel(
                    name='qotd-approval',
                    reason='QOTD setup: QOTD approval channel',
                    overwrites=overwrites
                )
                if qotd_approval_channel:
                    interaction_msg += f'\nQuestions for approval will appear in {qotd_approval_channel.mention}.'

            if qotd_channel and qotd_approval_channel:
                try:
                    query = '''
                        UPDATE guilds 
                        SET qotd_channel_id = $1, qotd_approval_channel_id = $2
                        WHERE guild_id = $3
                    '''
                    await self.bot.db.execute(query, qotd_channel.id, qotd_approval_channel.id, interaction.guild_id)
                except asyncpg.PostgresError as e:
                    await postgres.send_postgres_error_embed(bot=self.bot, query=query, error_msg=e)
                else:
                    interaction_msg += f'QOTD channel set to {channel.mention}.'

        await interaction.response.send_message(interaction_msg)


    @app_commands.command(name='channel', description='Get or edit QOTD channel')
    @app_commands.checks.has_permissions(manage_channels=True)
    async def qotd_edit_channel(self, interaction: discord.Interaction, channel: Optional[discord.TextChannel]) -> None:
        """Command to update QOTD channel."""
        # Required permissions for this command
        interaction_msg: str = ''
        # If channel given, update qotd channel
        if channel:
            if isinstance(channel, discord.TextChannel):
                # Required permissions for this command
                required_command_perms = {('read_messages', True), ('send_messages', True), ('embed_links', True), ('read_message_history', True)}
                missing_perms: list = utils.perms_check(self.bot, channel, required_command_perms)

                # If bot is missing permissions, send user list of missing permissions
                if missing_perms:
                    interaction_msg += f'Bot is missing these required permissions `{missing_perms}` in {channel.mention} for QOTD.'
                else:
                    try:
                        query = '''
                            UPDATE guilds 
                            SET qotd_channel_id = $1 
                            WHERE guild_id = $2
                            '''
                        await self.bot.db.execute(query, channel.id, interaction.guild_id)
                    except asyncpg.PostgresError as e:
                        await postgres.send_postgres_error_embed(bot=self.bot, query=query, error_msg=e)
                    else:
                        interaction_msg += f'QOTD is set to {channel.mention}.'
            else:
                interaction_msg += 'That is **not** a valid text channel.'
        else:
            # Fetch QOTD channel id from database
            try:
                query = '''
                    SELECT qotd_channel
                    FROM guilds 
                    WHERE guild_id = $1;
                '''
                qotd_channel_id = await self.bot.db.fetchval(query, interaction.guild_id) # Fetch channel id
            except asyncpg.PostgresError as e:
                await postgres.send_postgres_error_embed(bot=self.bot, query=query, error_msg=e)
                interaction_msg += 'Could not set up QOTD. Please try again.'
            else:
                if qotd_channel_id:
                    qotd_channel = await self.bot.fetch_channel(qotd_channel_id) # Fetch channel 
                
                    if qotd_channel:
                        interaction_msg += f'Current QOTD channel is {qotd_channel.mention}.'
                    else:
                        interaction_msg += f'The channel that QOTD is linked to does not exist. Please remove and set up QOTD again.'
                else:
                    interaction_msg += 'QOTD is not set up in this server.'

        await interaction.response.send_message(interaction_msg)


    @app_commands.command(name='remove', description='Removes QOTD from server.')
    @app_commands.describe(confirmation='Select "Yes" to confirm removal.')
    @app_commands.choices(confirmation=[
        app_commands.Choice(name='Yes', value=1),
        app_commands.Choice(name='No', value=0)
    ])
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.checks.bot_has_permissions(manage_channels=True)
    async def qotd_remove(
        self,
        interaction: discord.Interaction,
        confirmation: app_commands.Choice[int]
    ) -> None:
        '''Removes QOTD from the server.'''
        interaction_msg: str = ''

        if confirmation.value == 1:
            # Fetch QOTD channel from db
            try:
                query = '''
                    SELECT qotd_channel_id FROM guilds
                    WHERE guild_id = $1
                '''
                qotd_channel_id = await self.bot.db.fetchval(query, interaction.guild_id)
            except asyncpg.PostgresError as e:
                await postgres.send_postgres_error_embed(bot=self.bot, query=query, error_msg=e)
            else:
                if qotd_channel_id:
                    # Remove from database
                    try:
                        query = '''
                            UPDATE guilds
                            SET qotd_channel_id = NULL
                            WHERE guild_id = $1
                        '''
                        await self.bot.db.execute(query, interaction.guild_id)
                    except asyncpg.PostgresError as e:
                        await postgres.send_postgres_error_embed(bot=self.bot, query=query, error_msg=e)
                    else:
                        interaction_msg += 'QOTD removed.'
                else:
                    interaction_msg += 'QOTD is not set up. Use `/qotd setup`.'   
        else:
            interaction_msg += 'No action performed.'
        
        await interaction.response.send_message(interaction_msg)


    @app_commands.command(name='send', description='Manually sends "Question of the Day".')
    @app_commands.guilds(discord.Object(id=OWNER_GUILD_ID))
    @app_commands.checks.has_permissions(administrator=True)
    async def qotd_manual_send(self, interaction: discord.Interaction) -> None:
        # Get all pending channels to send QOTD to
        try:
            query = '''
                SELECT qotd_approval_channel_id
                FROM guilds
                WHERE qotd_approval_channel_id IS NOT NULL
            '''
            results = await self.bot.db.fetch(query)
        except asyncpg.PostgresError as e:
            await postgres.send_postgres_error_embed(bot=self.bot, query=query, error_msg=e)
        
        if results:
            channels_to_send: list = [res.get('qotd_approval_channel_id') for res in results]
            # Get question prompt and send to channel
            success: int = 0
            fails: int = 0
            for channel_id in channels_to_send:
                # Get question
                max_retries: int = 5
                retries: int = 0
                delay: int = 5
                while True:
                    question: str = get_question()
                    if question or retries >= max_retries:
                        break
                    else:
                        retries += 1
                        asyncio.sleep(delay)
                if retries >= max_retries:
                    return
                
                # Create embed for pending question
                pending_question_embed: discord.Embed = discord.Embed(
                    title='Pending QOTD',
                    color=0xa7c7e7,
                    timestamp=datetime.now()
                )
                pending_question_embed.add_field(name='Question', value=question, inline=False)
                pending_question_embed.add_field(name='Status', value='Pending', inline=False)

                # Send embed
                channel = await self.bot.fetch_channel(channel_id)
                message: discord.Message = await channel.send(embed=pending_question_embed, view=PendingQOTDView(self.bot))
                if message:
                    success += 1
                else:
                    fails += 1

        await interaction.response.send_message(f'Successfully sent QOTD to **{success} channels**.\n'
                                                f'Failed to send to **{fails} channels**.')
        

    @tasks.loop(time=[time(10, 0, 0, 0, tzinfo=gettz('US/Eastern'))], reconnect=True)
    async def qotd_send_question(self) -> None:
        '''Task sends QOTD @10AM EST daily.'''
        # Get all pending channels to send QOTD to
        try:
            query = '''
                SELECT qotd_approval_channel_id
                FROM guilds
                WHERE qotd_approval_channel_id IS NOT NULL
            '''
            results = await self.bot.db.fetch(query)
        except asyncpg.PostgresError as e:
            await postgres.send_postgres_error_embed(bot=self.bot, query=query, error_msg=e)
        
        if results:
            channels_to_send: list = [res.get('qotd_approval_channel_id') for res in results]
            # Get question prompt and send to channel
            for channel_id in channels_to_send:
                # Get question
                max_retries: int = 5
                retries: int = 0
                delay: int = 5
                while True:
                    question: str = get_question()
                    if question or retries >= max_retries:
                        break
                    else:
                        retries += 1
                        asyncio.sleep(delay)
                if retries >= max_retries:
                    continue # Continue to next iteration after max retries exceeded
                
                # Create embed for pending question
                pending_question_embed: discord.Embed = discord.Embed(
                    title='Pending QOTD',
                    color=0xa7c7e7,
                    timestamp=datetime.now()
                )
                pending_question_embed.add_field(name='Question', value=question, inline=False)
                pending_question_embed.add_field(name='Status', value='Pending', inline=False)

                # Send embed
                channel = await self.bot.fetch_channel(channel_id)
                message: discord.Message = await channel.send(embed=pending_question_embed, view=PendingQOTDView(self.bot))

    
    @qotd_send_question.error
    async def send_question_error(ctx, error):
        if isinstance(error, commands.ChannelNotFound):
            pass
    

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Qotd(bot))