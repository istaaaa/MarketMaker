# coding:utf-8

class MarketMaker:
    pass
    def __init__(self):
        #config.jsonの読み込み
        f = open('config/config.json', 'r', encoding="utf-8")
        config = json.load(f)


#!/usr/bin/python3
# coding: utf-8

import datetime
import time
import json
import ccxt
import bforder
import cryptowatch
#import talib as ta
import numpy as np
import pandas as pd




#configの読み込み
f = open('config/config.json', 'r', encoding="utf-8")
config = json.load(f)

order = bforder.BFOrder();

cryptowatch = cryptowatch.CryptoWatch()

bitflyer = ccxt.bitflyer({
'apiKey': config["key"],
'secret': config["secret"],
})

# 取引する通貨、シンボルを設定
COIN = 'BTC'
PAIR = 'BTC/JPY'

# プロダクトコードの指定 
PRODUCT = config["product_code"]

# ロット(単位はBTC)
LOT = config["lotSize"];

CANDLETERM = config["candleTerm"];

# 最小注文数(取引所の仕様に応じて設定)
AMOUNT_MIN = 0.001

# スプレッド閾値
SPREAD_ENTRY = 0.0001  # 実効スプレッド(100%=1,1%=0.01)がこの値を上回ったらエントリー
SPREAD_CANCEL = 0.0002 # 実効スプレッド(100%=1,1%=0.01)がこの値を下回ったら指値更新を停止

# 数量X(この数量よりも下に指値をおく)
AMOUNT_THRU = 1
AMOUNT_ASKBID = 0.5

# 実効Ask/BidからDELTA離れた位置に指値をおく
DELTA = 30

INVDELTA = -20

# 買い気配、売り気配に応じて主観的ファンダメンタル価格をずらす 
OFFSET = 2

ABSOFFSET = 100

PERTURB = 40

#------------------------------------------------------------------------------#
#log設定
import logging
logger = logging.getLogger('LoggingTest')
logger.setLevel(10)
fh = logging.FileHandler('log_mm_bf_' + datetime.datetime.now().strftime('%Y%m%d') + '_' + datetime.datetime.now().strftime('%H%M%S') + '.log')
logger.addHandler(fh)
sh = logging.StreamHandler()
logger.addHandler(sh)
formatter = logging.Formatter('%(asctime)s: %(message)s', datefmt="%Y-%m-%d %H:%M:%S")
fh.setFormatter(formatter)
sh.setFormatter(formatter)

#------------------------------------------------------------------------------#

# JPY残高を参照する関数
def get_asset():

    while True:
        try:
            value = bitflyer.fetch_balance(params = { "product_code" : PRODUCT })
            break
        except Exception as e:
            logger.info(e)
            time.sleep(1)
    return value

# JPY証拠金を参照する関数
def get_colla():

    while True:
        try:
            value = bitflyer.privateGetGetcollateral()
            break
        except Exception as e:
            logger.info(e)
            time.sleep(1)
    return value

# 板情報から実効Ask/Bid(=指値を入れる基準値)を計算する関数
def get_effective_tick(size_thru, rate_ask, size_ask, rate_bid, size_bid):

    while True:
        try:
            value = bitflyer.fetchOrderBook(PAIR,params = { "product_code" : PRODUCT })
            break
        except Exception as e:
            logger.info(e)
            time.sleep(2)

    i = 0
    s = 0
    while s <= size_thru:
        if value['bids'][i][0] == rate_bid:
            s += value['bids'][i][1] - size_bid
        else:
            s += value['bids'][i][1]
        i += 1

    j = 0
    t = 0
    while t <= size_thru:
        if value['asks'][j][0] == rate_ask:
            t += value['asks'][j][1] - size_ask
        else:
            t += value['asks'][j][1]
        j += 1

    time.sleep(0.5)
    return {'bid': value['bids'][i-1][0], 'ask': value['asks'][j-1][0]}

# 成行注文する関数
def market(side, size):

    while True:
        try:
            value = bitflyer.create_order(PAIR, type = 'market', side = side, amount = size,params = { "product_code" : PRODUCT })
            break
        except Exception as e:
            logger.info(e)
            time.sleep(2)
            #場当たり的な対処
            size = LOT;

    time.sleep(0.5)
    return value

# 指値注文する関数
def limit(side, size, price):

    while True:
        try:
            value = bitflyer.create_order(PAIR, type = 'limit', side = side, amount = size, price = price, params = { "product_code" : PRODUCT })
            break
        except Exception as e:
            logger.info(e)
            time.sleep(2)
            #場当たり的な対処
            size = LOT;

    time.sleep(0.5)
    return value

# 注文をキャンセルする関数
def cancel(id):

    try:
        value = bitflyer.cancelOrder(symbol = PAIR, id = id)
    except Exception as e:
        logger.info(e)

        # 指値が約定していた(=キャンセルが通らなかった)場合、
        # 注文情報を更新(約定済み)して返す
        value = get_status(id)

    time.sleep(0.5)
    return value

# 指定した注文idのステータスを参照する関数
def get_status(id):


    while True:
        try:
            value = bitflyer.private_get_getchildorders(params = {'product_code': PRODUCT, 'child_order_acceptance_id': id})[0]
            break
        except Exception as e:
            logger.info(e)
            time.sleep(2)

    # APIで受け取った値を読み換える
    if value['child_order_state'] == 'ACTIVE':
        status = 'open'
    elif value['child_order_state'] == 'COMPLETED':
        status = 'closed'
    else:
        status = value['child_order_state']

    # 未約定量を計算する
    remaining = float(value['size']) - float(value['executed_size'])

    time.sleep(0.1)
    return {'id': value['child_order_acceptance_id'], 'status': status, 'filled': value['executed_size'], 'remaining': remaining, 'amount': value['size'], 'price': value['price']}


def fromListToDF(candleStick):
    """
    Listのローソク足をpandasデータフレームへ．
    """
    date = [price[0] for price in candleStick]
    priceOpen = [int(price[1]) for price in candleStick]
    priceHigh = [int(price[2]) for price in candleStick]
    priceLow = [int(price[3]) for price in candleStick]
    priceClose = [int(price[4]) for price in candleStick]
    volume = [int(price[5]) for price in candleStick]
    date_datetime = map(datetime.datetime.fromtimestamp, date)
    dti = pd.DatetimeIndex(date_datetime)
    df_candleStick = pd.DataFrame({"open" : priceOpen, "high" : priceHigh, "low": priceLow, "close" : priceClose, "volume" : volume}, index=dti)
    return df_candleStick

def processCandleStick(candleStick, timeScale):
    """
    1分足データから各時間軸のデータを作成.timeScaleには5T（5分），H（1時間）などの文字列を入れる
    """
    df_candleStick = fromListToDF(candleStick)
    processed_candleStick = df_candleStick.resample(timeScale).agg({'open': 'first','high': 'max','low': 'min','close': 'last',"volume" : "sum"})
    processed_candleStick = processed_candleStick.dropna()
    return processed_candleStick

def zscore(x, axis = None):
    xmean = x.mean(axis=axis, keepdims=True)
    xstd  = np.std(x, axis=axis, keepdims=True)
    zscore = (x-xmean)/xstd
    return zscore


#------------------------------------------------------------------------------#

# 未約定量が存在することを示すフラグ
remaining_ask_flag = 0
remaining_bid_flag = 0

# 指値の有無を示す変数
pos = 'none'

#------------------------------------------------------------------------------#

logger.info('--------TradeStart--------')
logger.info('BOT TYPE      : MarketMaker @ bitFlyer')
logger.info('SYMBOL        : {0}'.format(PAIR))
logger.info('LOT           : {0} {1}'.format(LOT, COIN))
logger.info('SPREAD ENTRY  : {0} %'.format(SPREAD_ENTRY * 100))
logger.info('SPREAD CANCEL : {0} %'.format(SPREAD_CANCEL * 100))

# 残高取得
asset = float(get_asset()['info'][0]['amount'])
colla = float(get_colla()['collateral'])
logger.info('--------------------------')
logger.info('ASSET         : {0}'.format(int(asset)))
logger.info('COLLATERAL    : {0}'.format(int(colla)))
logger.info('TOTAL         : {0}'.format(int(asset + colla)))

#初期化 
trade_ask = {"status":'closed'}
trade_bid = {"status":'closed'}

# メインループ
while True:


    try:
        if "H" in CANDLETERM:
            candleStick = cryptowatch.getCandlestick(480, "3600")
        elif "30T" in CANDLETERM:
            candleStick = cryptowatch.getCandlestick(100, "1800")
        elif "15T" in CANDLETERM:
            candleStick = cryptowatch.getCandlestick(100, "900")
        elif "5T" in CANDLETERM:
            candleStick = cryptowatch.getCandlestick(100, "300")
        elif "3T" in CANDLETERM:
            candleStick = cryptowatch.getCandlestick(100, "180")
        else:
            candleStick = cryptowatch.getCandlestick(480, "60")
    except:
        logging.error("Unknown error happend when you requested candleStick")

    if CANDLETERM == None:
        df_candleStick = fromListToDF(candleStick)
    else:
        df_candleStick = processCandleStick(candleStick,CANDLETERM)

    #MACDの計算 
    #try:
        #macd, macdsignal, macdhist = ta.MACD(np.array(df_candleStick["close"][:], dtype='f8'), fastperiod=12, slowperiod=26, signalperiod=9);
    #except:
        #pass;

    #dmacdhist = np.gradient(macdhist)
    #Normdmacdhist = zscore(dmacdhist[~np.isnan(dmacdhist)])
    #absNormdmacdhist = np.abs(Normdmacdhist);



    # 未約定量の繰越がなければリセット
    if remaining_ask_flag == 0:
        remaining_ask = 0
    if remaining_bid_flag == 0:
        remaining_bid = 0

    # フラグリセット
    remaining_ask_flag = 0
    remaining_bid_flag = 0

    #positionを取得（指値だけだとバグるので修正取得）
    side , size = order.getmypos();

    if size == 0 and side =="":
        pos = 'none';
        trade_ask['status'] = 'closed';
        trade_bid['status'] = 'closed';
    else :
        pos = 'entry';
        if side == "SELL":
            trade_ask['status'] = 'open';
        if side == "BUY":
            trade_bid['status'] = 'open';

    # 自分の指値が存在しないとき実行する
    if pos == 'none':

        try:
            # 一つ前のspread            
            previousspread = spread;            
            # 板情報を取得、実効ask/bid(指値を入れる基準値)を決定する
            tick = get_effective_tick(size_thru=AMOUNT_THRU, rate_ask=0, size_ask=0, rate_bid=0, size_bid=0)
            ask = float(tick['ask'])
            bid = float(tick['bid'])
            # 実効スプレッドを計算する
            spread = (ask - bid) / bid

            tick = get_effective_tick(size_thru=AMOUNT_ASKBID, rate_ask=0, size_ask=0, rate_bid=0, size_bid=0)
            # askとbidを再計算する
            ask = float(tick['ask'])
            bid = float(tick['bid'])
            
            ticker = bitflyer.fetch_ticker('BTC/JPY', params = { "product_code" : "FX_BTC_JPY" })

            if int((ask + bid)/2) > int(ticker["last"]):
                trend = "buy"
            else:
                trend = "sell"

        except:
            pass;

        try:

            # 実効スプレッドが閾値を超えた場合に実行しない
            if spread < SPREAD_ENTRY and previousspread < SPREAD_ENTRY:

                # 前回のサイクルにて未約定量が存在すれば今回の注文数に加える
                amount_int_ask = LOT + remaining_bid
                amount_int_bid = LOT + remaining_ask
                
                tick = get_effective_tick(size_thru=AMOUNT_ASKBID, rate_ask=0, size_ask=0, rate_bid=0, size_bid=0)
                # askとbidを再計算する
                ask = float(tick['ask'])
                bid = float(tick['bid'])
                
                ticker = bitflyer.fetch_ticker('BTC/JPY', params = { "product_code" : "FX_BTC_JPY" })
                lastprice9 = int(ticker["last"])
                ticker = bitflyer.fetch_ticker('BTC/JPY', params = { "product_code" : "FX_BTC_JPY" })
                lastprice8 = int(ticker["last"])                
                ticker = bitflyer.fetch_ticker('BTC/JPY', params = { "product_code" : "FX_BTC_JPY" })
                lastprice7 = int(ticker["last"])                    
                
                
                ticker = bitflyer.fetch_ticker('BTC/JPY', params = { "product_code" : "FX_BTC_JPY" })
                lastprice6 = int(ticker["last"])
                ticker = bitflyer.fetch_ticker('BTC/JPY', params = { "product_code" : "FX_BTC_JPY" })
                lastprice5 = int(ticker["last"])                
                ticker = bitflyer.fetch_ticker('BTC/JPY', params = { "product_code" : "FX_BTC_JPY" })
                lastprice4 = int(ticker["last"])                
                
                ticker = bitflyer.fetch_ticker('BTC/JPY', params = { "product_code" : "FX_BTC_JPY" })
                lastprice3 = int(ticker["last"])
                ticker = bitflyer.fetch_ticker('BTC/JPY', params = { "product_code" : "FX_BTC_JPY" })
                lastprice2 = int(ticker["last"])                
                ticker = bitflyer.fetch_ticker('BTC/JPY', params = { "product_code" : "FX_BTC_JPY" })
                lastprice1 = int(ticker["last"])
                ticker = bitflyer.fetch_ticker('BTC/JPY', params = { "product_code" : "FX_BTC_JPY" })
                lastprice0 = int(ticker["last"])                
                
                lastprice = int((lastprice9 + lastprice8 + lastprice7 + lastprice6 + lastprice5 + lastprice4 + lastprice3 + lastprice2 + lastprice1 + lastprice0)/10)
                
                
                # 実効Ask/Bidからdelta離れた位置に指値を入れる
                if trend == "buy":
                    #trade_ask = limit('sell', amount_int_ask, ask - DELTA + int((spread * 10000) / 100) * ABSOFFSET)
                    #trade_bid = limit('buy', amount_int_bid, bid  + DELTA + int((spread * 10000) / 100) * ABSOFFSET)
                    #trade_ask = limit('sell', amount_int_ask, int((ask + bid)/2) + PERTURB)
                    #trade_bid = limit('buy', amount_int_bid, int((ask + bid)/2) - PERTURB)
                    trade_ask = limit('sell', amount_int_ask, lastprice + PERTURB + 20)
                    trade_bid = limit('buy', amount_int_bid, lastprice - PERTURB + 30)                    
                    
                    

                else:
                    #trade_ask = limit('sell', amount_int_ask, ask - DELTA - int((spread * 10000) / 100) * ABSOFFSET)
                    #trade_bid = limit('buy', amount_int_bid, bid  + DELTA - int((spread * 10000) / 100) * ABSOFFSET)
                    #trade_ask = limit('sell', amount_int_ask, int((ask + bid)/2) + PERTURB)
                    #trade_bid = limit('buy', amount_int_bid, int((ask + bid)/2) - PERTURB)
                    trade_ask = limit('sell', amount_int_ask, lastprice + PERTURB - 30)
                    trade_bid = limit('buy', amount_int_bid, lastprice - PERTURB - 20)                    
                    
                logger.info('--------------------------')
                logger.info('ask:{0}, bid:{1}, spread:{2}%'.format(int(ask * 100) / 100, int(bid * 100) / 100, int(spread * 10000) / 100))                       

                #logger.info('Normdmacdhist:%s ', Normdmacdhist[-1]);
                logger.info('Offset:%s ', int((spread * 10000) / 100) * OFFSET);
                logger.info('ABSOffset:%s ', int((spread * 10000) / 100) * ABSOFFSET);
                logger.info('trend:%s ', trend);

                logger.info('--------------------------')
                logger.info('ask:{0}, bid:{1}, spread:{2}%'.format(int(ask * 100) / 100, int(bid * 100) / 100, int(spread * 10000) / 100))

                trade_ask['status'] = 'open'
                trade_bid['status'] = 'open'
                pos = 'entry'

                logger.info('--------------------------')
                logger.info('entry')

                time.sleep(5)
        except:
            pass;

    # 自分の指値が存在するとき実行する
    if pos == 'entry':

        try:
                orders = bitflyer.fetch_orders(
	                symbol = PAIR,
	                params = { "product_code" : PRODUCT})

                openorders = bitflyer.fetch_open_orders(
	                symbol = PAIR,
	                params = { "product_code" : PRODUCT})

                trade_ask['status'] = "closed";
                trade_bid['status'] = "closed";

                for o in openorders:
                    if o["side"] == "sell":
                        trade_ask['status'] = "open";
                    elif o["side"] == "buy":
                        trade_bid['status'] = "open";
                    else:
                        trade_ask['status'] = "closed";
                        trade_bid['status'] = "closed";

                #最新の注文のidを取得する 
                for o in orders:

                    if o["side"] == "sell":
                        trade_ask['id']  = orders[-1]["id"];
                        # 注文ステータス取得
                        if trade_ask['status'] != 'closed':
                            trade_ask = get_status(trade_ask['id'])
                            break;
                for o in orders:
                    if  o["side"] == "buy":
                        trade_bid['id']  = orders[-1]["id"];
                        # 注文ステータス取得
                        if trade_bid['status'] != 'closed':
                            trade_bid = get_status(trade_bid['id'])
                            break;

                # 板情報を取得、実効Ask/Bid(指値を入れる基準値)を決定する
                tick = get_effective_tick(size_thru=AMOUNT_THRU, rate_ask=0, size_ask=0, rate_bid=0, size_bid=0)
                ask = float(tick['ask'])
                bid = float(tick['bid'])
                spread = (ask - bid) / bid


                logger.info('--------------------------')
                logger.info('ask:{0}, bid:{1}, spread:{2}%'.format(int(ask * 100) / 100, int(bid * 100) / 100, int(spread * 10000) / 100))
                logger.info('ask status:{0}, price:{1}'.format(trade_ask['status'], trade_ask['price']))
                logger.info('bid status:{0}, price:{1}'.format(trade_bid['status'], trade_bid['price']))
        except:
            pass;


        try:
            # Ask未約定量が最小注文量を下回るとき実行
            if trade_ask['status'] == 'open' and trade_ask['remaining'] <= AMOUNT_MIN:

                # 注文をキャンセル
                order.cancelAllOrder();

                # ステータスをCLOSEDに書き換える
                trade_ask['status'] = 'closed'

                # 未約定量を記録、次サイクルで未約定量を加えるフラグを立てる
                remaining_ask = float(trade_ask['remaining'])
                remaining_ask_flag = 1

                logger.info('--------------------------')
                logger.info('ask almost filled.')

            # Bid未約定量が最小注文量を下回るとき実行
            if trade_bid['status'] == 'open' and trade_bid['remaining'] <= AMOUNT_MIN:

                # 注文をキャンセル
                order.cancelAllOrder();

                # ステータスをCLOSEDに書き換える
                trade_bid['status'] = 'closed'

                # 未約定量を記録、次サイクルで未約定量を加えるフラグを立てる
                remaining_bid = float(trade_bid['remaining'])
                remaining_bid_flag = 1

                logger.info('--------------------------')
                logger.info('bid almost filled.')

            #スプレッドが閾値以上のときに実行する
            if spread > SPREAD_CANCEL:

                # Ask指値が最良位置に存在しないとき、指値を更新する
                if trade_ask['status'] == 'open':
                    if trade_ask['price'] != ask - DELTA:

                        # 指値を一旦キャンセル
                        order.cancelAllOrder();

                        # 注文数が最小注文数より大きいとき、指値を更新する
                        if trade_ask['remaining'] >= AMOUNT_MIN:
                            trade_ask = limit('sell', trade_ask['remaining'], ask - DELTA)
                            trade_ask['status'] = 'open'
                        # 注文数が最小注文数より小さく0でないとき、未約定量を記録してCLOSEDとする
                        elif AMOUNT_MIN > trade_ask['remaining'] > 0:
                            trade_ask['status'] = 'closed'
                            remaining_ask = float(trade_ask['remaining'])
                            remaining_ask_flag = 1

                    # 注文数が最小注文数より小さく0のとき、CLOSEDとする
                    else:
                        trade_ask['status'] = 'closed'

                # Bid指値が最良位置に存在しないとき、指値を更新する
                if trade_bid['status'] == 'open':
                    if trade_bid['price'] != bid + DELTA:

                        # 指値を一旦キャンセル
                        order.cancelAllOrder();

                        # 注文数が最小注文数より大きいとき、指値を更新する
                        if trade_bid['remaining'] >= AMOUNT_MIN:
                            trade_bid = limit('buy', trade_bid['remaining'], bid + DELTA)
                            trade_bid['status'] = 'open'
                        # 注文数が最小注文数より小さく0でないとき、未約定量を記録してCLOSEDとする
                        elif AMOUNT_MIN > trade_bid['remaining'] > 0:
                            trade_bid['status'] = 'closed'
                            remaining_bid = float(trade_bid['remaining'])
                            remaining_bid_flag = 1
                        # 注文数が最小注文数より小さく0のとき、CLOSEDとする
                        else:
                            trade_bid['status'] = 'closed'

                #おそうじする 

                tick = get_effective_tick(size_thru=AMOUNT_ASKBID, rate_ask=0, size_ask=0, rate_bid=0, size_bid=0)
                # askとbidを再計算する
                ask = float(tick['ask'])
                bid = float(tick['bid'])

                if side == "SELL" and trade_bid['status'] == "closed":
                        amount_int_bid = LOT + remaining_ask
                        trade_bid = limit('buy', amount_int_bid, bid + DELTA + int((spread * 10000) / 100) * OFFSET)
                        trade_bid['status'] = 'open'
                if side == "BUY" and trade_ask['status'] == "closed":
                        amount_int_ask = LOT + remaining_bid
                        trade_ask = limit('sell', amount_int_ask, ask - DELTA - int((spread * 10000) / 100) * OFFSET)
                        trade_bid['status'] = 'open'
        except:
            pass;

        # Ask/Bid両方の指値が約定したとき、1サイクル終了、最初の処理に戻る
        try:
            if trade_ask['status'] == 'closed' and trade_bid['status'] == 'closed':
                pos = 'none'

                logger.info('--------------------------')
                logger.info('completed.')
        except:
            pass;

    time.sleep(5)


