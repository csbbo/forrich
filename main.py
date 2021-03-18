from flask import Flask, jsonify, request
from flask_pymongo import PyMongo
from flask_apscheduler import APScheduler

from pypinyin import Style, pinyin
from concurrent.futures import ThreadPoolExecutor

import tushare
import datetime
import time
import base64
import logging


logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)

# ================ init
class Config:
    SCHEDULER_API_ENABLED = True
    SCHEDULER_TIMEZONE = 'Asia/Shanghai'
    MONGO_URI = "mongodb://127.0.0.1:27017/forrich"
    # MONGO_URI = "mongodb://forrich_mongo:27017/forrich"

    DEBUG = True
    HOST = '0.0.0.0'
    PORT = '9000'
    TU_SHARE_TOKE = 'NTk1YjU2YTIxNDA5NmQwMzlmNTNmYzJhNGMzNzc5YTIyMTdiZDUwNGViMWYwYjlhMjRiMDc5OTE='


app = Flask(__name__)
app.config.from_object(Config())

mongo = PyMongo(app)

scheduler = APScheduler()
scheduler.init_app(app)
scheduler.start()

pro = tushare.pro_api(str(base64.b64decode(bytes(Config.TU_SHARE_TOKE, encoding='utf-8')), encoding='utf-8'))


# ================ class and function
class Macd():
    def __init__(self, price_list, slow_ema_n, quick_ema_n, dif_n):
        self.price_list = price_list
        self.quick_ema_n = quick_ema_n
        self.slow_ema_n = slow_ema_n
        self.dif_n = dif_n

    def cal_ema(self, price_list, n):
        ema_list = []
        for index, price in enumerate(price_list):
            if index == 0:
                ema_list.append(price)
            else:
                pre_ema = ema_list[index-1]
                ema_list.append((price * 2 / (n+1)) + (pre_ema * (n-1) / (n+1)))
        return ema_list

    def cal_dif(self, price_list, slow_ema_n, quick_ema_n):
        slow_ema_list = self.cal_ema(price_list, slow_ema_n)
        quick_ema_list = self.cal_ema(price_list, quick_ema_n)
        dif_list = []
        for i in range(len(price_list)):
            dif_list.append(quick_ema_list[i] - slow_ema_list[i])
        return dif_list

    def get_dif_dea(self, price_list, slow_ema_n, quick_ema_n, dif_n):
        dif_list = self.cal_dif(price_list, slow_ema_n, quick_ema_n)
        dea_list = self.cal_ema(dif_list, dif_n)
        return dif_list, dea_list

    def pass_filter(self):
        dif_list, dea_list = self.get_dif_dea(self.price_list, self.slow_ema_n, self.quick_ema_n, self.dif_n)
        if len(dif_list) < 20:
            return False

        if dea_list[-2] < dif_list[-2] and dea_list[-1] > dif_list[-1] and abs(dea_list[-1]) < 0.05:
            return True
        return False


def save_stocks():
    fields = ['ts_code', 'symbol', 'name', 'area', 'industry', 'fullname', 'enname', 'market', 'exchange', 'curr_type', 'list_status', 'list_date', 'delist_date', 'is_hs']
    fields_str = ','.join(fields)
    df = pro.query('stock_basic', exchange='', list_status='L', fields=fields_str)

    def short_pinyin(name):
        s = ''
        for letter in pinyin(name, style=Style.FIRST_LETTER, strict=False):
            s += letter[0][0]
        return s

    data = {}
    for _, row in df.iterrows():
        for field in fields:
            data[field] = row[field]
        data['pinyin'] = short_pinyin(row['name'])
        mongo.db.stocks.update_one({'ts_code': row['ts_code']}, {'$set': data}, upsert=True)


def save_stock_price_history(ts_code, start_date, end_date):
    df = pro.daily(ts_code=ts_code, start_date=start_date, end_date=end_date, fields='trade_date,close')

    price = df['close'].to_list()
    price.reverse()

    trade_date = df['trade_date'].to_list()
    trade_date.reverse()

    data = {
        'trade_date': trade_date,
        'price': price
    }
    mongo.db.history.update_one({'ts_code': ts_code}, {'$set': data}, upsert=True)


def save_all_stocks_price_history():
    today = datetime.date.today().strftime('%Y%m%d')
    df = pro.query('stock_basic', exchange='', list_status='L', fields='ts_code,list_date')
    pool = ThreadPoolExecutor(max_workers=60)
    for index, row in df.iterrows():
        ts_code = row['ts_code']
        list_date = row['list_date']
        pool.submit(save_stock_price_history, ts_code, list_date, today)
        if (index+1) % 500 == 0:    # The tushare interface is limited to 500 requests per minute
            time.sleep(62)


# ================ scheduler
@scheduler.task('cron', id='scheduler_task', day_of_week='mon-fri', hour=15, minute=30)
def scheduler_task():
    now_time = (datetime.datetime.utcnow() + datetime.timedelta(hours=8)).strftime('%Y-%m-%d: %H:%M:%S')
    logger.info(f'task run in {now_time}')
    save_stocks()
    save_all_stocks_price_history()


# ================ route
@app.route('/demo', methods=['GET', 'POST'])
def demo():
    args = request.args
    json = request.json
    method = request.method
    resp = {
        "method": method,
        "agent": None
    }
    if bool(args) is True:
        resp.update(args)
    if bool(json) is True:
        resp.update(json)
    return jsonify(resp)


@app.route('/', methods=['GET'])
def query():
    search = request.args.getlist('s')
    if len(search) == 1:
        search = search[0]
        filt = {'$or': [
            {'pinyin': {'$regex': search}},
            {'name': {'$regex': search}},
            {'ts_code': {'$regex': search}},
            {'symbol': {'$regex': search}},
        ]}
    else:
        filt = {'$or': [
            {'pinyin': {'$in': search}},
            {'name': {'$in': search}},
            {'ts_code': {'$in': search}},
            {'symbol': {'$in': search}},
        ]}
    stocks = mongo.db.stocks.find(filt)

    resp = []
    for stock in stocks:
        df = tushare.get_realtime_quotes(stock.get('symbol'))
        price = float(df.at[0, 'price'])
        pre_close = float(df.at[0, 'pre_close'])
        rose = f"{round((price - pre_close) / pre_close * 100, 3)}%"
        resp.append({'price': price, 'rose': rose})
    return str(resp)


@app.route('/pick', methods=['GET'])
def self_selection():
    content = ""
    historys = mongo.db.history.find()
    for history in historys:
        price_list = history.get('price')
        ts_code = history.get('ts_code')
        macd = Macd(price_list, 26, 12, 9)
        if macd.pass_filter():
            content += f'<tr><td>{ts_code}</td></tr>'
    return f'<table style="width:20px; margin:auto">{content}</table>'


@app.route('/task', methods=['GET'])
def get_price_history():
    save_stocks()
    save_all_stocks_price_history()
    return jsonify({"resp": "success"})


if __name__ == '__main__':
    app.debug = Config.DEBUG
    app.run(host=Config.HOST, port=Config.PORT)
