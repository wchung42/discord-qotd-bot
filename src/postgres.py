import discord
from discord.ext import commands
from datetime import datetime

async def send_postgres_error_embed(bot: commands.Bot, query: str, error_msg: str) -> discord.Embed:
        error_embed = discord.Embed(
            title=f'{bot.user.name} Has Encountered a Postgres Error',
            color=discord.Color(0xFF0000),
            timestamp=datetime.now()
        )
        error_embed.add_field(name='Query', value=query, inline=False)
        error_embed.add_field(name='Error Message', value=error_msg, inline=False)
        error_embed.add_field(name='Time', value=error_embed.timestamp, inline=False)
        error_embed.set_footer(text=f'Sent by {bot.user.name}')

        owner = await bot.fetch_user(bot.owner_id)
        await owner.send(embed=error_embed)