from flask import Flask, jsonify, request
from flask_pymongo import PyMongo
from flask_apscheduler import APScheduler
import tushare
from pypinyin import Style, pinyin


class Config:
    SCHEDULER_API_ENABLED = True
    MONGO_URI = "mongodb://127.0.0.1:27017/forrich"

    DEBUG = True
    HOST = '0.0.0.0'
    PORT = '9000'
    TU_SHARE_TOKE = '595b56a214096d039f53fc2a4c3779a2217bd504eb1f0b9a24b07991'


app = Flask(__name__)
app.config.from_object(Config())

mongo = PyMongo(app)

scheduler = APScheduler()
scheduler.init_app(app)
scheduler.start()

ts = tushare.pro_api(Config.TU_SHARE_TOKE)


@app.route('/test', methods=['GET', 'POST'])
def get_user():
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
    stocks = mongo.db.stocks.find({'$or': [
        {'short_pinyin': {'$in': search}},
        {'name': {'$in': search}},
        {'code': {'$in': search}},
    ]})

    resp = []
    for stock in stocks:
        df = tushare.get_realtime_quotes(stock.get('code'))
        price = float(df.at[0, 'price'])
        pre_close = float(df.at[0, 'pre_close'])
        resp.append(
            {
                # 'name': stock.get('name'),
                'price': price,
                'rose': f"{round((price - pre_close) / pre_close * 100, 3)}%",
            }
        )
    return str(resp)


@scheduler.task('cron', id='update_stocks', day_of_week='*', hour=9, minute=15, second=0)
def update_stocks_info():
    fields = 'ts_code,symbol,name,area,industry,fullname,enname,market,exchange,curr_type,list_status,list_date,' \
             'delist_date,is_hs '
    df = ts.query('stock_basic', exchange='', list_status='L', fields=fields)

    def short_pinyin(name):
        s = ''
        for letter in pinyin(name, style=Style.FIRST_LETTER, strict=False):
            s += letter[0][0]
        return s

    for row in df.itertuples():
        item = {
            'ts_code': row[1],
            'code': row[2],
            'name': row[3],
            'short_pinyin': short_pinyin(row[3]),
            'area': row[4],
            'industry': row[5],
            'fullname': row[6],
            'enname': row[7],
            'market': row[8],
            'exchange': row[9],
            'curr_type': row[10],
            'list_status': row[11],
            'list_date': row[12],
            'delist_date': row[13],
            'is_hs': row[14],
        }
        mongo.db.stocks.update_one({'code': item['code']}, {'$set': item}, upsert=True)
    return jsonify({"resp": "success"})


if __name__ == '__main__':
    app.debug = Config.DEBUG
    app.run(host=Config.HOST, port=Config.PORT)
