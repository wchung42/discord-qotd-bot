import discord
from discord.ext import commands
from datetime import datetime
import asyncpg
import random
import postgres

class Events(commands.Cog):
    '''
    Events Cog
    '''
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        

    async def cog_load(self) -> None:
        print('* Events module READY')
    

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.guild) -> None:
        '''Adds server info to database when bot joins a new server.'''
        # Add guild to database with default prefix (?) and current members
        try:
            query = '''
                INSERT INTO guilds(guild_id, prefix) 
                VALUES ($1, $2)
                '''
            await self.bot.db.execute(query, guild.id, self.bot.command_prefix)
        except asyncpg.PostgresError as e:
            await postgres.send_postgres_error_embed(bot=self.bot, query=query, error_msg=e)


    @commands.Cog.listener()
    async def on_guild_remove(self, guild) -> None:
        '''Clean up when bot leaves the guild.'''
        async with self.bot.db.acquire() as conn:
            tr = conn.transaction()
            await tr.start()
            success: bool = False
            while not success:
                try:
                    # Remove guild from guilds
                    query: str = '''
                        DELETE FROM guilds 
                        WHERE guild_id = $1
                        '''
                    await self.bot.db.execute(query, guild.id)

                    # Remove all pending qotd from guild database
                    query = '''
                        DELETE FROM qotd_pending_messages
                        WHERE guild_id = $1
                    '''
                    await self.bot.db.execute(query, guild.id)
                except asyncpg.PostgresError as e:
                    await tr.rollback()
                    await postgres.send_postgres_error_embed(bot=self.bot, query=query, error_msg=e)
                else:
                    success = True
                    await tr.commit()


    # #TODO - Error handler
    async def cog_command_error(self, ctx, error: Exception) -> None:
        '''Error handler for events module'''
        if isinstance(error, discord.HTTPException):
            await ctx.send(f'HTTPException raised.\nError: {error}', ephemeral=True)
        if isinstance(error, discord.NotFound):
            await ctx.send(f'NotFound exception raised.\nError: {error}', ephemeral=True)
        if isinstance(error, discord.Forbidden):
            await ctx.send(f'Forbidden error raised.\nError: {error}', ephemeral=True)
        else:
            await ctx.send(f'Unknown error raised.\nError: {error}')


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Events(bot))