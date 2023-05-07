import discord
from discord.ext import commands
from discord.ext.commands import Greedy, Context
from typing import Literal, Optional
import asyncio

class Owner(commands.Cog):
    '''
    Owner Cog
    '''
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot


    async def cog_load(self) -> None:
        print('* Owner module READY')


    @commands.command(name='sync')
    @commands.guild_only()
    @commands.is_owner()
    async def sync(self, ctx: Context, guilds: Greedy[discord.Object], spec: Optional[Literal["~", "*", "^"]] = None) -> None:
        '''
        ?sync -> global sync
        ?sync ~ -> sync current guild
        ?sync * -> copies all global app commands to current guild and syncs
        ?sync ^ -> clears all commands from the current guild target and syncs (removes guild commands)
        ?sync id_1 id_2 -> syncs guilds with id 1 and 2
        '''
        if not guilds:
            if spec == '~':
                synced = await self.bot.tree.sync(guild=ctx.guild)
            elif spec == '*':
                self.bot.tree.copy_global_to(guild=ctx.guild)
                synced = await self.bot.tree.sync(guild=ctx.guild)
            elif spec == '^':
                self.bot.tree.clear_commands(guild=ctx.guild)
                await self.bot.tree.sync(guild=ctx.guild)
                synced = []
            else:
                synced = await self.bot.tree.sync()
            await ctx.send(f"Synced {len(synced)} commands {'globally' if spec is None else 'to the current guild.'}")
            return
        
        ret = 0
        for guild in guilds:
            try:
                await self.bot.tree.sync(guild=guild)
            except discord.HTTPException:
                pass
            else:
                ret += 1
        
        await ctx.send(f'Synced the tree to {ret}/{len(guilds)}.')


    @commands.command(name='load', hidden=True)
    @commands.is_owner()
    async def load_cog(self, ctx, *, cog: str) -> None:
        '''Loads cog given as argument.'''
        try:
            await self.bot.load_extension(f'cogs.{cog}')
        except Exception as e:
            await ctx.send(f'**[Error]:** {type(e).__name__} - {e}')
        else:
            await ctx.send(f'**{cog} module** loaded successfully.')

    
    @commands.command(name='unload', hidden = True)
    @commands.is_owner()
    async def unload_cog(self, ctx, *, cog: str) -> None:
        '''Unloads cog give as argument.'''
        try:
            await self.bot.unload_extension(f'cogs.{cog}')
        except Exception as e:
            await ctx.send(f'**[Error]:** {type(e).__name__} - {e}')
        else:
            await ctx.send(f'**{cog} module** unloaded successfully.')


    @commands.command(name='reload', hidden = True)
    @commands.is_owner()
    async def reload_cog(self, ctx, *, cog: str) -> None:
        '''Reloads cog given as argument.'''
        try:
            await self.bot.reload_extension(f'cogs.{cog}')
        except Exception as e:
            await ctx.send(f'**[Error]:** {type(e).__name__} - {e}')
        else:
            await ctx.send(f'**{cog} module** successfully reloaded.')


    @commands.command(name='disconnect', aliases=['logout', 'stopbot', 'close'], hidden=True)
    @commands.is_owner()
    async def logout(self, ctx) -> None:
        '''Disconnects the bot from discord.'''
        await ctx.send('**Logged out successfully.**')
        await self.bot.close()


    @logout.error
    async def logout_error(ctx, error) -> None:
        '''Error handling for logout command.'''
        if isinstance(error, commands.CheckFailure):
            await ctx.send(f'{ctx.author.mention}** You do not have permission to use that command.**')
        else:
            raise error


    @commands.command(name='updatestatus', aliases=['us'], hidden=True)
    @commands.is_owner()
    async def updatestatus(self, ctx, *, status: str) -> None:
        '''Update status of the bot.'''
        await self.bot.change_presence(activity=discord.Game(status), status=discord.Status.online)
        await ctx.send(f'Changed status to: {status}')

    
async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Owner(bot))