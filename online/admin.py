from django.contrib import admin
from .models import PrivateChatRoom, PrivateChatMember, PrivateChatInvite, OnlineSession, MultiplayerRoom, Friend, DirectChat

admin.site.register(PrivateChatRoom)
admin.site.register(PrivateChatMember)
admin.site.register(PrivateChatInvite)
admin.site.register(OnlineSession)
admin.site.register(MultiplayerRoom)
admin.site.register(Friend)
admin.site.register(DirectChat)
