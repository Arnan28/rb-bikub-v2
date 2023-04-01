from bitkub import Bitkub
import pandas as pd
from datetime import datetime
import pytz
from songline import Sendline
import hashlib
import hmac
import json
import requests

# API info
API_HOST = 'https://api.bitkub.com'
API_KEY = '.......................................'
API_SECRET = b'...................................'            # มี b อยู่หน้า 'secret key'
SECRET = '........................................'            # ไม่มี b อยู่หน้า 'secret key' 

token = '..........................................'

messenger = Sendline(token)

bitkub = Bitkub(api_key=API_KEY, api_secret=SECRET)
bitkub.servertime()
pd.to_datetime(bitkub.servertime(), unit='s')

posframe = pd.read_csv('config_.csv')
asv = posframe.quantity.sum()
# df = pd.DataFrame(posframe)
# print(posframe)
ticker = pd.DataFrame(bitkub.ticker()) #sym='THB_BTC')

lim_pct = 0.02
lim_value = 10
period = 5*60*24*4000   #5*300*5 tf5min   #5*60*300 #

Sma_W = 5*60*24*7       #1week

###########################  update api v2 ###########################
def json_encode(data):
	return json.dumps(data, separators=(',', ':'), sort_keys=True)

def sign(data):
	j = json_encode(data)
	# print('Signing payload: ' + j)
	h = hmac.new(API_SECRET, msg=j.encode(), digestmod=hashlib.sha256)
	return h.hexdigest()
#######################################################################

def changpos(curr, buy=True):
    if buy:
        posframe.loc[posframe.Currency == curr, 'position'] = 0      #1
    # else:
    #     posframe.loc[posframe.Currency == curr, 'position'] = 0
    # posframe.to_csv('position', index=False)

def gethourldata(symbol):
    data = bitkub.tradingview(sym= symbol, int=5, 
                                        frm=(bitkub.servertime()-period), 
                                        to=bitkub.servertime())

    frame = pd.DataFrame(data)
    # frame = frame.iloc[:,:6]
    frame = frame[['t','o','h','l','c','v','s']]
    frame.columns = ['Timestamp','Open','High','Low','Close','Volume','status']
    frame['Timestamp'] = pd.to_datetime(frame['Timestamp'], unit='s').dt.tz_localize('Asia/Bangkok')
    return frame
df = gethourldata('BTC_THB')

def applytechnicals(df):
    df['FastEMA'] = df.Close.ewm(7).mean()
    df['SlowEMA'] = df.Close.ewm(25).mean()
    df['SMA_'] = df.Close.rolling(20).mean()  
    df['stddev'] = df.Close.rolling(20).std()
    df['Upper'] = df.SMA_ + 2 * df.stddev
    df['Lower'] = df.SMA_ - 2 * df.stddev    
    df['SMA_W'] = df.Close.rolling(Sma_W).mean()  
applytechnicals(df)    

def balance(coin_):
    bal = pd.DataFrame(bitkub.wallet())
    balance = bal['result'][coin_] 
    return balance

def orderhistory(crr,coins,ptv):
    hisframe = bitkub.my_open_history(sym=crr, p=1, lmt=1)
    hisframe = pd.DataFrame(hisframe['result']) 
    hisframe['coin'] = coins
    hisframe['portvalue'] = ptv
    orderhis = hisframe[['date','side','amount','rate','fee','credit','coin','portvalue']]
    orderhis.to_csv('order_record_.csv', mode='a', header=False, index=False)    
    
    order    = hisframe[['side','amount','rate']][0:1]
    amnt = order.amount
    rat  = order.rate
    order['value'] = float(amnt) * float(rat)
    print(f'{crr}',  order.set_index('side'))


def report(curr,qty,price,amts,value,re_sell,asv,thb,ptv,smawk):
    print(f' Rebalancing: Fix {curr} {qty} ')
    print(f' Asset {asv} Baht: {thb}')
    print(f' Port: {ptv} Price: {price}')
    print(f' amt : {amts} weekly: {smawk}')        
    print(f' Lt.V: {value} P/L: {re_sell}')
    print('----------------------------------')

# def withdraw(ptv,asv):                                                        #ทดสอบการถอนจริงได้แล้ว เหลือเขียนตรรกะในการถอนว่าจะดึงเป็นอาทิตย์หรือมูลค่าเพิ่มขึ้นตามที่กำหนด 
#     if  float(ptv) < float(asv):
#         pass
#     elif float(ptv) > float(asv):
#         amtw = 1025
#         bitkub.fiat_withdraw(id='บช', amt=amtw)   
#         print(f' Withdraw {amtw}'  )

def trader(curr):
    qty = posframe[posframe.Currency == curr].quantity.values[0]
    coins  = posframe[posframe.Currency == curr].coins.values[0]
    crr    = posframe[posframe.Currency == curr].crr.values[0]
    pct_   = posframe[posframe.Currency == curr].pct.values[0]
    hw     = posframe[posframe.Currency == curr].HW.values[0]                    # ระบุจำนวนเหรียญในวอลเล็ท กรณีไม่อยากนำเงินหรือเหรียญเข้ามาในโบรกเกอร์ทั้งหมด 
    
    df = gethourldata(curr)   
    applytechnicals(df)   
    thb = balance('THB')
    am = balance(coins)
    lastrow = df.iloc[-1]
    price = lastrow.Close
    smawk = '%.2f'%(lastrow.SMA_W)
    
    amts = am + hw                                                             # ทำเพื่อนำจำนวนเหรียญคริปโตในวอลเล็ทมาบวกกับในโบรก
    value  = '%.2f'%(float(amts) * float(price))
    re_buy  = '%.2f'%(float(qty) - float(value))
    re_sell = '%.2f'%(float(value) - float(qty))
    pct = float(qty) * pct_ #lim_pct
    ptv = '%.2f'%(thb + asv)


    if posframe[posframe.Currency == curr].quantity.values[0]:
        # withdraw(ptv,asv)
        report(curr,qty,price,amts,value,re_sell,asv,thb,ptv,smawk)      

        if price < float(smawk):
            pass   

        else:

            if price < lastrow.Lower or price > lastrow.SMA_ and float(re_sell) <= lim_value:

                if  float(re_buy) <= lim_value:
                    pass

                elif float(re_buy) >= lim_value and float(re_buy) >= pct:

                    ## Library bitkub.เก่า เนื่องจากทางบิทคับได้มีการอัพเดทเฉพาะคำสั่งซื้อขายเส้นใหม่ api v2 
                    # bitkub.place_bid(sym= crr, 
                    #                  amt= re_buy, 
                    #                  typ='market')


                #############################################  update api v2 ####################################################
                    
                    # check server time
                    response = requests.get(API_HOST + '/api/servertime')
                    ts = int(response.text)

                    # place bid
                    header = {
                        'Accept': 'application/json',
                        'Content-Type': 'application/json',
                        'X-BTK-APIKEY': API_KEY,
                    }
                    data = {
                        'sym': crr,
                        'amt': re_buy,                # THB amount you want to spend
                        'rat': price,
                        'typ': 'market',
                        'ts': ts,
                    }
                    signature = sign(data)
                    data['sig'] = signature

                    # print('Payload with signature: ' + json_encode(data))
                    response = requests.post(API_HOST + '/api/market/v2/place-bid', headers=header, data=json_encode(data))

                    # print('Response: ' + response.text)

                ####################################################################################################################                       

                    time.sleep(3)
                    orderhistory(crr,coins,ptv)    
                    print('__________________________________')                
                    # changpos(curr, buy=True)

                    # messenger.sendtext(f' Buy {curr} : {price} : values {re_buy} ')
            

            elif  price > lastrow.Upper or price < lastrow.SMA_ and float(re_buy) <= lim_value:

                if  float(re_sell) <= lim_value:
                    pass

                elif float(re_sell) >= lim_value and float(re_sell) >= pct:

                        sell = '%.4f'%(float(re_sell) / price)

                        # bitkub.place_ask(sym= crr, 
                        #                  amt= sell,  
                        #                  typ='market') 


                #############################################  update api v2 ####################################################

                        # check server time
                        response = requests.get(API_HOST + '/api/servertime')
                        ts = int(response.text)
                        # print('Server time: ' + response.text)

                        # place ask
                        header = {
                            'Accept': 'application/json',
                            'Content-Type': 'application/json',
                            'X-BTK-APIKEY': API_KEY,
                        }
                        data = {
                            'sym': crr,
                            'amt': sell,                                # BTC amount you want to sell
                            'rat': price,
                            'typ': 'market',
                            'ts': ts,
                        }
                        signature = sign(data)
                        data['sig'] = signature

                        # print('Payload with signature: ' + json_encode(data))
                        response = requests.post(API_HOST + '/api/market/v2/place-ask', headers=header, data=json_encode(data))

                        # print('Response: ' + response.text)

                ####################################################################################################################                       

                        time.sleep(3)
                        orderhistory(crr,coins,ptv)                 
                        print('__________________________________')                
                        # changpos(curr, buy=True)

                        # messenger.sendtext(f' Sell {curr} : {price} : values {re_sell} ')

    else:
        print('Nothing')


import time

while True:
    time.sleep(60)
    for coin in posframe.Currency:
        try:
            trader(coin)
        except Exception as e:
            print(f' error: {e}')
            pass
        except :
            continue






#==========================================================================================================#

