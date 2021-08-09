#!/usr/bin/env python
"""Telegram Music bot"""

import os, sys, yaml, re, math, json, logging, pickle
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, BaseFilter, CallbackQueryHandler, InlineQueryHandler, run_async
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from pathlib import Path
from telegram_music_collection import TelegramMusicCollection
from functools import partial
import time

class TelegramMusicBot:
    
    #def __init__(self, nickname, token, hello_html, collection_path, telegram_fileid_file, track_rates_file, bot_name, id3based = False, broadcast_messages = []):
    def __init__(self, **bot_parameters):

        self.nickname = bot_parameters.get("nickname")
        self.hello_html = bot_parameters.get("hello_html")
        
        logging.info('Collection init')
        self.bot_files = TelegramFileId(bot_parameters.get("telegram_fileid_file"))
        self.rates = TrackRates(bot_parameters.get("track_rates_file"))
        self.collection = TelegramMusicCollection(bot_parameters.get("collection_path"), bot_parameters.get("id3based"))

        self.updater = Updater(token=bot_parameters.get("token"), workers=32)
        self.dispatcher = self.updater.dispatcher

        
        logging.info('Registering handlers...') 

        hlo_ch = partial(hello_command_handler, hello_html=self.hello_html)
        unkn_ch = partial(unknown_command, hello_html=self.hello_html)
        som_ch = partial(message_handler,collection=self.collection, rates=self.rates)
        rndm_ch = partial(random_command_handler, collection=self.collection, rates=self.rates)
        lks_ch = partial(liked_command_handler, collection=self.collection, rates=self.rates)
        t100_ch = partial(top100_command_handler, collection=self.collection, rates=self.rates)
        ply_ch = partial(play_command, collection=self.collection, bot_files=self.bot_files)
        rate_ch = partial(rate_command, collection=self.collection, bot_files=self.bot_files, rates=self.rates)
        btn_ch = partial(button_callback, collection=self.collection, bot_files=self.bot_files, rates=self.rates)
        play_command_filter = PlayCommandsFilter()
        rate_command_filter = RateCommandsFilter()

        self.dispatcher.add_handler(MessageHandler(Filters.text, som_ch))
        self.dispatcher.add_handler(CommandHandler('help', hlo_ch))
        self.dispatcher.add_handler(CommandHandler('start', hlo_ch))
        self.dispatcher.add_handler(CommandHandler('random', rndm_ch))
        self.dispatcher.add_handler(CommandHandler('mylikes', lks_ch))
        self.dispatcher.add_handler(CommandHandler('top100', t100_ch))
        self.dispatcher.add_handler(MessageHandler(play_command_filter, ply_ch))
        self.dispatcher.add_handler(MessageHandler(rate_command_filter, rate_ch))

        self.dispatcher.add_handler(MessageHandler(Filters.command, unkn_ch))

        self.dispatcher.add_handler(CallbackQueryHandler(btn_ch))
        self.dispatcher.add_handler(InlineQueryHandler(inline_handler))
        
        # log all errors
        self.dispatcher.add_error_handler(error)
        logging.info('Init done') 

    def start(self):
        #Start the bot
        logging.info('Start polling...') 
        self.updater.start_polling()



@run_async
def search_on_message_handler(bot, update, collection, bot_files):
    logging.info('New update: %s', update) 
    send_search_result_message(bot=bot, chat_id=update.message.chat_id, message_id=update.message.message_id, search_str=update.message.text, collection=collection, bot_files=bot_files)

@run_async
def message_handler(bot, update, collection,  rates):
    """searching collection with message text"""
    logging.info('New update: %s', update)
    track_list = collection.search(update.message.text)
    show_track_list(bot=bot, chat_id=update.message.chat_id, message_id=update.message.message_id, track_list=track_list, collection=collection, rates=rates)
    
@run_async
def button_callback(bot, update, collection, bot_files, rates):
    logging.info('New update: %s', update)
    logging.info('Callback data: %s', update.callback_query.data)
    if (update.callback_query.data == '/random'):
        random(bot, update.callback_query.message.chat_id, update.callback_query.message.message_id, collection, update.callback_query)
        update.callback_query.answer()
        return()
    if re.search('upd[slt]w', update.callback_query.data):
        page_setup = json.loads(update.callback_query.data)
        update_page(bot=bot, 
                    chat_id=update.callback_query.message.chat_id, 
                    message=update.callback_query.message, 
                    page_setup=page_setup,
                    collection=collection, 
                    rates=rates) 
        update.callback_query.answer()
        return()
    if (update.callback_query.data == '_useless_button_'):
        update.callback_query.answer()
        return()
        
    

def list2text(track_list, collection, rates, highlight_rated=False, hide_rate=True):
    """
    Generates message text on given track list
    """
    text_html = "<b>Search results:</b>\n"
    for caption in track_list:
        play_command = '/play_' + collection.hash(caption)
        rate_command = '/rate_' + collection.hash(caption)
        text_html += '%s\n<i>Download: </i>%s\n👍 %s\n\n' % (caption, play_command, rate_command)
    logging.debug(text_html)
    return text_html



def show_track_list(bot, chat_id, message_id, track_list, collection, rates, highlight_rated=False, hide_rate=True, page_type="search"):
    """
    Sends track list without keyboard if results are short or send it with keyboard otherwise
    """
    page_size = 6
    pages = math.ceil(len(track_list)/page_size)
    if pages <= 1:
        content = list2text(track_list, collection, rates)
        bot.send_message(chat_id=chat_id, reply_to_message_id=message_id,  text=content, parse_mode='HTML')
    else:
        if page_type == "search":
            current_page_setup = {'q': 'updsw', 'wsz': page_size, 'wpos': 1, 'now': pages}
            next_page_setup = {'q': 'updsw', 'wsz': page_size, 'wpos': 2, 'now': pages}
        elif page_type == "likes":
            current_page_setup = {'q': 'updlw', 'wsz': page_size, 'wpos': 1, 'now': pages}
            next_page_setup = {'q': 'updlw', 'wsz': page_size, 'wpos': 2, 'now': pages}
        elif page_type == "top100":
            current_page_setup = {'q': 'updtw', 'wsz': page_size, 'wpos': 1, 'now': pages}
            next_page_setup = {'q': 'updtw', 'wsz': page_size, 'wpos': 2, 'now': pages}
        keyboard = get_page_keyboard(current_page_setup)
        logging.debug(str(track_list[:page_size]))
        content = list2text(track_list[:page_size], collection, rates=rates)
        bot.send_message(chat_id=chat_id, reply_to_message_id=message_id,  text=content, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))
 



def get_page_content(message, page_setup, collection, rates, highlight_rated=False, hide_rate=True):
    """
    Returns page html content
    """
    if page_setup["q"] == "updsw":
        search_result_list = collection.search(message.reply_to_message.text)
        from_index = (page_setup['wpos'] - 1) * page_setup['wsz']
        to_index = page_setup['wpos'] * page_setup['wsz']
        return list2text(search_result_list[from_index:to_index], collection, rates, highlight_rated, hide_rate)
    elif page_setup["q"] == "updlw":
        track_list = rates.get_liked_tracks(message.chat.username)
        track_list = [t for t in track_list if collection.exists(t)]
        from_index = (page_setup['wpos'] - 1) * page_setup['wsz']
        to_index = page_setup['wpos'] * page_setup['wsz']
        return list2text(track_list[from_index:to_index], collection, rates, highlight_rated, hide_rate)
    elif page_setup["q"] == "updtw":
        track_list = rates.get_top100()
        track_list = [t for t in track_list if collection.exists(t)]
        from_index = (page_setup['wpos'] - 1) * page_setup['wsz']
        to_index = page_setup['wpos'] * page_setup['wsz']
        return list2text(track_list[from_index:to_index], collection, rates, highlight_rated, hide_rate)

def get_page_keyboard(page_setup):
    """
        Returns page keyboard based on page_setup
    """
    keyboard = []
    if page_setup['now'] == page_setup['wpos']:
        previous_page_setup = page_setup.copy()
        previous_page_setup['wpos'] -= 1
        buttons = []
        buttons.append({"cap": "<", "callback": json.dumps(previous_page_setup)})
        buttons.append({"cap": '%d/%d' % (page_setup['wpos'], page_setup['now']), "callback": "_useless_button_"})
        keyboard = [[InlineKeyboardButton(text=b["cap"], callback_data=b["callback"]) for b in buttons]]
    elif page_setup['wpos'] == 1:
        next_page_setup = page_setup.copy()
        next_page_setup['wpos'] += 1
        buttons = []
        buttons.append({"cap": '1/%d' % (page_setup['now']), "callback": "_useless_button_"})
        buttons.append({"cap": ">", "callback": json.dumps(next_page_setup)})
        keyboard = [[InlineKeyboardButton(text=b["cap"], callback_data=b["callback"]) for b in buttons]]
    else:
        previous_page_setup = page_setup.copy()
        previous_page_setup['wpos'] -= 1
        next_page_setup = page_setup.copy()
        next_page_setup['wpos'] += 1
        buttons = []
        buttons.append({"cap": "<", "callback": json.dumps(previous_page_setup)})
        buttons.append({"cap": '%d/%d' % (page_setup['wpos'], page_setup['now']), "callback": "_useless_button_"})
        buttons.append({"cap": ">", "callback": json.dumps(next_page_setup)})
        keyboard = [[InlineKeyboardButton(text=b["cap"], callback_data=b["callback"]) for b in buttons]]
    return keyboard

def update_page(bot, chat_id, message, page_setup, collection, rates, highlight_rated=False, hide_rate=True):
    """
    updates paged track list message
    """
    
    content = get_page_content(message, page_setup, collection, rates, highlight_rated, hide_rate)
    keyboard = get_page_keyboard(page_setup)
    bot.edit_message_text(chat_id=chat_id, message_id=message.message_id, text=content, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))


def random(bot, chat_id, message_id, collection, callback_query=None):
    """
    returns a message with 3 random tracks
    """
    text_html = '<b>Random tracks:</b>\n'
    for i in range(3):
        caption = collection.random()
        play_command = '/play_' + collection.hash(caption)
        rate_command = '/rate_' + collection.hash(caption)
        text_html += '%s\n<i>Download: </i>%s\n👍 %s\n\n' % (caption, play_command,rate_command)
    keyboard = [[InlineKeyboardButton(text="↻", callback_data="/random")]]
    if callback_query:
        bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=text_html, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        bot.send_message(chat_id=chat_id, reply_to=message_id,  text=text_html, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))

@run_async       
def random_command_handler(bot, update, collection, rates):
    logging.info('New update: %s', update)
    random(bot, update.message.chat_id, update.message.message_id, collection)

@run_async       
def liked_command_handler(bot, update, collection, rates):
    logging.info('New update: %s', update)
    track_list = rates.get_liked_tracks(update.message.chat.username)
    track_list = [t for t in track_list if collection.exists(t)]
    show_track_list(bot=bot, chat_id=update.message.chat_id, message_id=update.message.message_id, track_list=track_list, collection=collection, rates=rates, page_type="likes")    
    
@run_async       
def top100_command_handler(bot, update, collection, rates):
    logging.info('New update: %s', update)
    track_list = rates.get_top100()
    logging.debug(str(track_list))
    track_list = [t for t in track_list if collection.exists(t)]
    logging.debug(str(track_list))
    show_track_list(bot=bot, chat_id=update.message.chat_id, message_id=update.message.message_id, track_list=track_list, collection=collection, rates=rates, page_type="top100")    

def send_audio_file_by_hash(bot, update, chat_id, hash, collection, bot_files):
    """
    sends file associated with caption in mds collection
    """ 
    
    caption = collection.get_by_hash(hash)
    
    if collection.exists(caption):
        audio_file = open(str(collection.path(caption)) , 'rb')
    else:
        return

    file_id = bot_files.get(collection.filename(caption))
    
    logging.info('Will send file %s with id %s' % (str(audio_file), str(file_id)))
    if file_id: 
        try:
            sent = bot.send_audio(chat_id=chat_id, audio=file_id, caption=caption, title=collection.title(caption), performer=collection.author(caption), duration=collection.length(caption), timeout=60)
            logging.info('File sent, got: %s', sent)
        except TelegramError:
            sent = bot.send_audio(chat_id=chat_id, audio=audio_file, caption=caption, title=collection.title(caption), performer=collection.author(caption), duration=collection.length(caption), timeout=60)
            logging.info('File sent, got: %s', sent)
            bot_files.set(collection.filename(caption), sent['audio']['file_id'])
    else:
        sent = bot.send_audio(chat_id=chat_id, audio=audio_file, caption=caption, title=collection.title(caption), performer=collection.author(caption), duration=collection.length(caption), timeout=60)
        logging.info('File sent, got: %s', sent)
        bot_files.set(collection.filename(caption), sent['audio']['file_id'])
    
    audio_file.close()

def inline_handler(bot, update):
    """
    inline query handler
    """
    logging.info('New update: %s', update) 
    



@run_async    
def hello_command_handler(bot,update,hello_html):
    """Send a message when /start received
    """
    
    logging.info('New update: %s', update) 
    keyboard = [[InlineKeyboardButton(text="I'm feeling lucky", callback_data='/random')]]
    bot.send_message(chat_id=update.message.chat_id, text=hello_html, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))

@run_async
def play_command(bot, update, collection, bot_files):
    """plays an audio file on /play_hash command
    """
    logging.info('New update: %s', update) 
    if not '/play_' in update.message.text:
        return()
    mds_track_hash = update.message.text.partition('_')[2]
    send_audio_file_by_hash(bot, update, update.message.chat_id, mds_track_hash, collection, bot_files)
        
@run_async
def rate_command(bot, update, collection, bot_files, rates):
    """plays an audio file on /play_hash command
    """
    logging.info('New update: %s', update) 
    if not '/rate_' in update.message.text:
        return()
    mds_track_hash = update.message.text.partition('_')[2]
    rates.rate(update.message.chat.username, collection.get_by_hash(mds_track_hash))
    print("%s rated %s!" % (update.message.chat.username, collection.get_by_hash(mds_track_hash)))

     

def unknown_command(bot, update, hello_html):
    """Logs unknown command"""
    logging.info('New update: %s', update) 
    hello_command_handler(bot, update, hello_html)

def error(bot, update, error):
    """Log Errors caused by Updates."""
    logging.warning('Update "%s" caused error "%s"', update, error)

class TelegramFileId:
    """
    TelegramFileId represents telegram bot filename: id dictionary
    """
    def __init__(self, pickle_filename):
        """
        if pickle_filename exists - reads dictionary from it
        if file not exists - creates it and dumps to it
        """
        self.file = Path(pickle_filename)
        if self.file.exists():
            self.idict = pickle.load(open(self.file, 'rb'))
        else:
            self.idict = {}
            pickle.dump(self.idict, open(self.file, 'wb'))

    

    def dump(self):
        """
        Serializing to file
        """
        pickle.dump(self.idict, open(self.file, 'wb'))

    def set(self, filename, id):
        self.idict[filename] = id
        self.dump()
    

    def remove(self, filename):
        if filename in self.idict.keys():
            del(self.idict[filename])
            self.dump()

    def __str__(self):
        return str(self.idict)
    
    def get(self, name):
        if name in self.idict.keys():
            return self.idict[name]
        else:
            return None

class TrackRates:
    """
    Stores track rates idict[track_name][user_name] = int(time.time())
    """
    def __init__(self, pickle_filename):
        """
        if pickle_filename exists - reads dictionary from it
        if file not exists - creates it and dumps to it
        """
        self.file = Path(pickle_filename)
        if self.file.exists():
            self.idict = pickle.load(open(self.file, 'rb'))
        else:
            self.idict = {}
            pickle.dump(self.idict, open(self.file, 'wb'))

    

    def dump(self):
        """
        Serializing to file
        """
        pickle.dump(self.idict, open(self.file, 'wb'))

    def rate(self, user_name, track_name):
        """rates track_name by user_name. idict keeps last "like" of song by user. """
        if track_name not in self.idict.keys(): self.idict[track_name] = {}
        self.idict[track_name][user_name] = int(time.time())
        self.dump()
    
    def __str__(self):
        return str(self.idict)
    
    def get(self, track_name):
        if track_name in self.idict.keys():
            return len(self.idict[track_name])
        else:
            return 0

    def get_liked_tracks(self, user_name):
        """Returns list of user liked tracks"""
        l= [t for t in self.idict.keys() if user_name in self.idict[t].keys()]
        print("likes: " + str(l))
        return l
    
    def get_top100(self):
        """Returns list of top 100 rated tracks"""
        top_list = sorted(self.idict.keys(),key=lambda t: len(self.idict[t]), reverse=True)[:101]
        logging.debug(str(top_list))
        return top_list
        


def upload_collection(bot, update):
    """
    uploads full MDS collection. the purpose is to update telegram file ids for quick upload in future.
    """
    
    logging.info('New update: %s', update) 
    global bot_files
    global mds    
    global ok_to_upload_collection 
    
    ok_to_upload_collection = True
    
    for caption in collection.mds_dict:
        logging.info('Uploading %s', caption) 
        if not ok_to_upload_collection: return
        send_audio_file_by_hash(bot, update, update.message.chat_id, collection.hash(caption))

def stop_uploading_collection(bot, update):
    """
    stops collection upload
    """
    logging.info('New update: %s', update)
    global ok_to_upload_collection 
    logging.info('ok_to_upload_collection = %s', ok_to_upload_collection)
    ok_to_upload_collection = False
    logging.info('ok_to_upload_collection = %s', ok_to_upload_collection)
    
    
class PlayCommandsFilter(BaseFilter):
    """
    filter for /play_hash commands
    """ 
    def filter(self, message):
        return bool(message.text and message.text.startswith('/play'))

class RateCommandsFilter(BaseFilter):
    """
    filter for /play_hash commands
    """ 
    def filter(self, message):
        return bool(message.text and message.text.startswith('/rate'))



ok_to_upload_collection = True


def main():
    try:
        bot_params = yaml.load(open(sys.argv[1]))
    except:
        print("Usage: %s bot_config.yaml" % (sys.argv[0]))
        sys.exit() 

    lfh = logging.FileHandler('bots/log/'+ bot_params['nickname'] + '.log')
    lfh.setLevel(logging.INFO)
    lfh.setFormatter(logging.Formatter(fmt='%(asctime)s %(funcName)s %(levelname)s %(message)s'))
#adding handler to a root logger
    #logging.getLogger('').setLevel(logging.DEBUG)
    logging.getLogger('').addHandler(lfh)
    
    if 'id3based' not in bot_params.keys(): bot_params['id3based'] = False
    mds_bot = TelegramMusicBot(**bot_params)
    
    mds_bot.start()


if __name__ == '__main__':
    main()


