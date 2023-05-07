# utils.py
#
# This file contains useful utility and helper functions.


import discord
from typing import Union, Tuple, List

def perms_check(obj: Union[discord.User, discord.Member, discord.Role], 
        channel: Union[discord.TextChannel, discord.ForumChannel, discord.TextChannel, discord.CategoryChannel],
        required_perms: set) -> List[str]:
    '''Returns the set difference between member permissions and channel permissions'''
    # Get the channel perms for the member
    member_perms: List[Tuple] = {p for p in channel.permissions_for(obj) if p[1]}
    # Compare perms to required, return difference as list of perms names
    perms_diff: List[Tuple] = required_perms.difference(member_perms)
    missing_perms = [p[0] for p in perms_diff]
    return missing_perms