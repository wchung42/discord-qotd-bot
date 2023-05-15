import discord
from discord.ext import commands
import asyncio
import asyncpg
import aiohttp
import os
import logging
import postgres
from dotenv import load_dotenv

load_dotenv()

DEFAULT_PREFIX = 'q!'

# Enable Discord Intents
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

#--------------------------------------------------------------------
# Define Question Bot class
#--------------------------------------------------------------------
class QuestionBot(commands.Bot):
    def __init__(self, session):
        super().__init__(
            command_prefix=DEFAULT_PREFIX,
            intents=intents,
            application_id=int(os.getenv('APPLICATION_ID')),
            owner_id=int(os.getenv('OWNER_ID')),
            activity=discord.Game('with questions.'), 
            status=discord.Status.online,
            help_command=None,
        )
        self.session = session
        self.config_token = str(os.getenv('BOT_TOKEN'))
        self.version = str(os.getenv('VERSION'))
        self.DEFAULTPREFIX = DEFAULT_PREFIX
        self.owner_guild_id = os.getenv('OWNER_GUILD_ID')

        logging.basicConfig(level=logging.INFO)

        self.initial_extensions = []
        for file in os.listdir('./src/cogs'):
            if file.endswith('.py'):
                self.initial_extensions.append(f'cogs.{file[:-3]}')
    

    async def get_prefix(self, message):
        if not message.guild:
            return commands.when_mentioned_or(DEFAULT_PREFIX)(self, message)

        # Fetch prefix from DB
        prefix: str = DEFAULT_PREFIX
        async with self.db.acquire() as conn:
            tr = conn.transaction()
            await tr.start()
            try:
                query: str = 'SELECT prefix FROM guilds WHERE guild_id = $1'
                prefix: str = await self.db.fetchval(query, message.guild.id)
                if not prefix:
                    query = 'INSERT INTO guilds(guild_id, prefix) VALUES ($1, $2)'
                    await self.db.execute(query, message.guild.id, DEFAULT_PREFIX)
            except asyncpg.PostgresError as e:
                await tr.rollback()
                await postgres.send_postgres_error_embed(self, query, e)
            else:
                await tr.commit()
        return commands.when_mentioned_or(prefix)(self, message)


    # Initialize database pool
    async def create_db_pool(self):
        self.db = await asyncpg.create_pool(
            database=os.getenv('PGDATABASE'),
            user=os.getenv('PGUSER'), 
            password=os.getenv('PGPASSWORD'),
            host=os.getenv('PGHOST'),
            port=os.getenv('PGPORT'), 
        )
        if self.db:
            print('Database connection established.')
        else:
            print('[ERROR]: Database connection could not be established')


    # Setup function
    async def setup_hook(self) -> None:
        print('Running setup...')
        self.session = aiohttp.ClientSession()
        await self.create_db_pool() # Connect to database

        # Create tables if they do not exist
        async with self.db.acquire() as conn:
            tr = conn.transaction()
            await tr.start()
            try:
                query: str = '''
                    CREATE TABLE IF NOT EXISTS guilds (
                        guild_id BIGINT PRIMARY KEY,
                        prefix VARCHAR(5),
                        qotd_approval_channel_id BIGINT,
                        qotd_channel_id BIGINT,
                        unasked_questions TEXT[],
                        asked_questions TEXT[]
                    )
                '''
                await self.db.execute(query)
            except asyncpg.PostgresError as e:
                await tr.rollback()
                await postgres.send_postgres_error_embed(self.bot, query, e)
                print('[ERROR]: Guilds creation...FAILED')
            else:
                await tr.commit()
        
        # Load all cogs
        for ext in self.initial_extensions:
            await self.load_extension(ext)

        print('Setup complete.')


    async def close(self) -> None:
        await super().close()
        await self.session.close()


    async def on_ready(self) -> None:
        await self.wait_until_ready()
        print('Online.')


    async def on_message(self, message: discord.Message):
        if message.author.id == self.user.id: # ignore self
            return
        # if isinstance(message.channel, discord.DMChannel): # ignore dms
        #     return
        await self.process_commands(message)


#--------------------------------------------------------------------
# Main driver function
#--------------------------------------------------------------------
async def main():
    async with aiohttp.ClientSession() as session:
        async with QuestionBot(session) as bot:
            await bot.start(bot.config_token, reconnect=True)


asyncio.run(main())