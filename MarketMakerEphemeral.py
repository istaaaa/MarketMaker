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
import requests
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
SPREAD_ENTRY = 0.0000  # 実効スプレッド(100%=1,1%=0.01)がこの値を上回ったらエントリー
SPREAD_CANCEL = 0.0000 # 実効スプレッド(100%=1,1%=0.01)がこの値を下回ったら指値更新を停止

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

spread = 0

vixFlag = 0

callback = 'stay';

signedsize = 0;

minLOT = 0.01


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
            size = minLOT;

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
            size = minLOT;

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

#rciのdの計算
def dofrci(itv,src):
    from scipy.stats import rankdata
    sum = 0.0
    for i in range(itv, 0, -1):
        date_rank = itv - i + 1
        price_rank = (itv - rankdata(src)[i-1] + 1)
        sum = sum + pow( (date_rank - price_rank) ,2)
        #pprint("hiduke = {},  price={},  juni={},  goukei={}".format(date_rank, src[i-1], price_rank, sum) )
    
    return sum
   
#rciの計算
def calc_rci(src, term):
    
    listnull = [None]
    itv = term
    rcinull = listnull * itv
    rci_tmp = [   (1.0 - 6.0 * dofrci(itv,src[i-itv:i]) / (itv * itv * itv - itv)) * 100.0   for i in range(itv,len(src))]
    rci = rcinull + rci_tmp
    
    return rci

def vixfix(close, low):
    prd = 22
    bbl = 20
    mult = 2.0
    lb = 50
    ph = 0.85
    pl = 1.01

    wvf = (pd.Series(close).rolling(prd, 1).max() - low) / pd.Series(close).rolling(prd, 1).max() * 100

    sDev = mult * pd.Series(wvf).rolling(bbl, 1).std()
    midLine = pd.Series(wvf).rolling(bbl, 1).mean()

    lowerBand = midLine - sDev
    upperBand = midLine + sDev
    rangeHigh = pd.Series(wvf).rolling(lb, 1).max() * ph
    rangeLow = pd.Series(wvf).rolling(lb, 1).min() * pl

    #緑が点灯しているときはエントリーしない
    if wvf[len(wvf)-1] > rangeHigh[len(wvf)-1] or wvf[len(wvf)-1] > upperBand[len(wvf)-1]:
        return 'buy'
        #print("VIX: 緑")
    elif wvf[len(wvf)-2] > rangeHigh[len(wvf)-2] or wvf[len(wvf)-2] > upperBand[len(wvf)-2]:
        if wvf[len(wvf)-1] < rangeHigh[len(wvf)-1] or wvf[len(wvf)-1] < upperBand[len(wvf)-1]:
            #print('VIX: 緑からグレー')
            1+1
            #return 'buy'
    #赤が点灯しているときはエントリーしない
    elif wvf[len(wvf)-1] < rangeLow[len(wvf)-1] or wvf[len(wvf)-1] < lowerBand[len(wvf)-1]:
        return 'sell'
        #print("VIX: 赤")
    elif wvf[len(wvf)-2] < rangeLow[len(wvf)-2] or wvf[len(wvf)-2] < lowerBand[len(wvf)-2]:
        if wvf[len(wvf)-1] > rangeLow[len(wvf)-1] or wvf[len(wvf)-1] > lowerBand[len(wvf)-1]:
            #print('VIX: 赤からグレー')
            1+1
            #return 'sell'
    else:
        pass
        #print("VIX: グレー")

    return 'stay'


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

    #3期間RCIの計算 
    rcirangetermNine = calc_rci(df_candleStick["close"][:],3);
    logger.info('rcirangetermNine:%s ', rcirangetermNine[-1]);

    # 未約定量の繰越がなければリセット
    if remaining_ask_flag == 0:
        remaining_ask = 0
    if remaining_bid_flag == 0:
        remaining_bid = 0

    #VIX戦略
    LOW_PRICE = 3
    CLOSE_PRICE = 4
    PERIOD = 60  # どの時間足で運用するか(例: 5分足 => 60秒*5 =「300」,1分足 => 60秒 =「60」を入力)

    nowvix = str(int(datetime.datetime.now().timestamp()))
    resvix = requests.get('https://api.cryptowat.ch/markets/bitflyer/btcfxjpy/ohlc?periods=' + str(PERIOD) + '&after=' + str(int(nowvix)-PERIOD*100) + '&before=' + nowvix)
    ohlcvvix = resvix.json()
    ohlcvRvix = list(map(list, zip(*ohlcvvix['result'][str(PERIOD)])))
    lowvix = np.array(ohlcvRvix[LOW_PRICE])
    closevix = np.array(ohlcvRvix[CLOSE_PRICE])
    callback = vixfix(closevix, lowvix)


    if callback == 'buy':
        #Buy
        vixFlag = 1
    elif callback == 'sell':
        #Sell
        vixFlag = 2
    else:
        #Stay
        vixFlag = 0;

    #VIXflagのログ
        logger.info('vixflag:%s ', vixFlag);

    # フラグリセット
    remaining_ask_flag = 0
    remaining_bid_flag = 0

    #positionを取得（指値だけだとバグるので修正取得）
    side , size = order.getmypos();

    if side == "SELL":
        signedsize = -size;
    if side == "BUY":
        signedsize = size;

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
    if pos == 'none' or pos == 'entry':

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
            
            ticker = bitflyer.fetch_ticker('BTC/JPY', params = { "product_code" : PRODUCT })

            if int((ask + bid)/2) > int(ticker["last"]):
                trend = "sell"
            else:
                trend = "buy"

        except:
            pass;

        try:

            # 実効スプレッドが閾値を超えた場合に実行する
            if spread > SPREAD_ENTRY:

                # 前回のサイクルにて未約定量が存在すれば今回の注文数に加える
                amount_int_ask = LOT + remaining_bid
                amount_int_bid = LOT + remaining_ask
                
                tick = get_effective_tick(size_thru=AMOUNT_ASKBID, rate_ask=0, size_ask=0, rate_bid=0, size_bid=0)
                # askとbidを再計算する
                ask = float(tick['ask'])
                bid = float(tick['bid'])

                #実効Ask/Bidからdelta離れた位置に指値を入れる
                if rcirangetermNine[-1] < 85 and trend == "buy" and vixFlag == 0 and size < 0.3:
                    trade_bid = limit('buy', amount_int_bid, (ticker["bid"]))                    
                    time.sleep(0.2)
                    order.cancelAllOrder();
                    
                elif rcirangetermNine[-1] > -85 and trend == "sell" and vixFlag == 0 and size < 0.3:
                    trade_ask = limit('sell', amount_int_ask, (ticker["ask"]))
                    time.sleep(0.2)
                    order.cancelAllOrder();

                elif side == "SELL":
                    if rcirangetermNine[-1] < -85 or rcirangetermNine[-1] > 85 :
                        trade_bid = market('buy', size)
                        time.sleep(1)
                        order.cancelAllOrder();

                elif side == "BUY":
                    if rcirangetermNine[-1] < -85 or rcirangetermNine[-1] > 85 :
                        trade_ask = market('sell', size)
                        time.sleep(1)
                        order.cancelAllOrder();

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

                time.sleep(1)
        except:
            pass;

 
