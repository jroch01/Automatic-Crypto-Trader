import time
import yfinance as yf  # data source
import datetime
import pandas as pd
import openpyxl
import warnings

working_directory = "<path to working directory>"
yf.set_tz_cache_location("<path to desired cache storage location>")  # set cache folder location

warnings.simplefilter(action='ignore', category=FutureWarning)  # prevent warnings from clogging terminal


class TradingBot:

    def __init__(self):
        self.initialized_time = str(datetime.datetime.now())[:19]
        self.save_to_excel = True
        self.save_thresh = 5  # number of completed trades before saving history to excel if option is enabled
        self.profit_sell_thresh = 3.1  # 0.75 [%] minimum threshold to be met before selling for a profit
        self.loss_sell_thresh = -1.8  # -0.5   [%] maximum percentage drop before cutting losses
        self.loop_fee = 0.0025  # 0.25% fee to swap assets on Loopring L2
        self.swap_fee = 1-self.loop_fee
        self.current_asset = "None"  # current asset being held
        self.current_asset_direction = "None"  # track direction of asset being held
        self.current_asset_15min_percentage = 0  # [%] keep track of current asset's percent change over last 15 minutes
        self.price_change_thresh = 0.05  # [%] percentage to determine if asset is Rising, Falling, or Flat

        self.bankroll = 1000.0  # [$] used to simulate using real money
        self.purchase_price = 0.0
        self.sell_price = 0.0
        self.asset_owned = "None"
        self.quantity = 0
        self.buy_count = 0
        self.sell_count = 0
        self.net_value = 0
        self.ticker = ["AAVE-USD", "BTU-USD", "BZRX-USD", "LINK-USD", "CRV-USD", "DPR-USD", "DGD-USD",
                       "ENS-USD", "ETH-USD", "PNK-USD", "LRC-USD", "PNT5794-USD", "RENBTC-USD", "UNI7083-USD"]


        self.fee_total = 0.0
        self.buy_thresh = 0
        self.sell_thresh = 0
        self.profit_sell_count = 0
        self.loss_sell_count = 0
        self.save_signal = 0
        self.transaction_history = [[str(datetime.datetime.now())[:19], self.current_asset, self.purchase_price,
                                     self.sell_price, self.quantity,
                                     self.purchase_price * self.quantity * self.swap_fee -
                                     self.sell_price * self.quantity * self.swap_fee,
                                     self.bankroll, self.profit_sell_count + self.loss_sell_count, self.fee_total]]
        self.transaction_table = pd.DataFrame(self.transaction_history, columns=["Date/Time", "Ticker",
                                                                                 "Purchase Price ($)", "Sell Price ($)",
                                                                                 "Quantity", "Profit ($)",
                                                                                 "Total Value ($)", "Trade Number",
                                                                                 "Total Fees ($)"])

    def buy_asset(self, ticker):
        bought_at = yf.download(tickers=f'{ticker}', period="15m", interval="1m")
        self.purchase_price = bought_at['Close'][-1]
        prev_bankroll = self.bankroll
        self.bankroll = self.bankroll*self.swap_fee
        self.fee_total += prev_bankroll - self.bankroll
        print(f"Buying power: ${self.bankroll}")
        self.net_value = self.bankroll
        self.quantity = self.bankroll/self.purchase_price
        self.asset_owned = f'{ticker}'
        self.bankroll = 0.0
        print(f"Purchased {self.quantity} {self.asset_owned} \t Total fees: ${self.fee_total:.2f}")
        self.buy_count += 1

    def sell_asset(self, ticker):
        sold_at = yf.download(tickers=f'{ticker}', period="15m", interval="1m")  # get ticker info from Yahoo Finance
        self.sell_price = sold_at['Close'][-1]
        prev_bankroll = self.sell_price*self.quantity
        self.bankroll = self.sell_price*self.quantity*self.swap_fee
        self.net_value = self.bankroll
        self.fee_total += prev_bankroll - self.bankroll
        self.transaction_history += [[str(datetime.datetime.now())[:19], self.current_asset, self.purchase_price,
                                     self.sell_price, self.quantity, self.sell_price*self.quantity*self.swap_fee -
                                     self.purchase_price*self.quantity*self.swap_fee,
                                     self.sell_price*self.quantity*self.swap_fee,
                                     self.profit_sell_count+self.loss_sell_count, self.fee_total]]

        self.transaction_table = pd.DataFrame(self.transaction_history,
                                              columns=["Date/Time", "Ticker", "Purchase Price ($)",
                                                       "Sell Price ($)", "Quantity", "Profit ($)",
                                                       "Total Value ($)", "Trade Number", "Total Fees ($)"])

        if self.save_signal % self.save_thresh == 0 and self.save_to_excel == True:  # save history to Excel file
            date = str(datetime.datetime.now())[:10]
            self.transaction_table.to_excel(f"{working_directory}\\auto_trader_{date}.xlsx",
                                            sheet_name='1.25% Sell Thresh', index=False, header=True)
            self.save_signal = 0

        print(f"Sold {self.quantity} {self.asset_owned} at a price of {self.sell_price} for ${self.bankroll} \t Total fees: ${self.fee_total:.2f}")

        self.quantity = 0
        self.purchase_price = 0.0
        self.asset_owned = "None"
        self.sell_count += 1


    def asset_analysis(self, ticker, time_frame):
        data = yf.download(tickers=ticker, period=time_frame, interval="1m")
        historical_price = data["Close"]

        # Determine current price direction of movement
        current_price = data["Close"][-1]  # current price as of this minute
        minute_15_price = data['Close'][-15]  # price as of 15 minutes ago
        minute_15_percent_change = (current_price - minute_15_price)/current_price*100

        if minute_15_percent_change > self.price_change_thresh:
            price_direction = "Rising"
        elif minute_15_percent_change < -self.price_change_thresh:
            price_direction = "Falling"
        else:
            price_direction = "Flat"

        # Analyze volatility
        max_price = max(historical_price)
        min_price = min(historical_price)
        avg_price = sum(historical_price)/len(historical_price)
        volume = data["Volume"]
        volume_check = sum(volume)
        max_volatility = max_price - min_price
        volatility_percent = (1 - ((min_price - max_volatility)/min_price))*100
        sell_count = 0
        sell_list = []
        buy_count = 0
        buy_list = []
        thresh = 0.9  # looking to buy/sell within % of 24 hour historical low/high price
        sell_thresh = (max_price - avg_price)*thresh + avg_price
        buy_thresh = (avg_price - min_price)*(1 - thresh) + min_price
        threshed_volatility = sell_thresh - buy_thresh
        threshed_volatility_percent = (1 - ((buy_thresh - threshed_volatility)/buy_thresh))*100

        for i in range(len(historical_price)):

            if historical_price[i] > sell_thresh:
                # print(f"Selling point: {historical_price[i]}")
                sell_list.append(historical_price[i])
                sell_count += 1

            if historical_price[i] < buy_thresh:
                # print(f"Buying point: {historical_price[i]}")
                buy_list.append(historical_price[i])
                buy_count += 1

        return threshed_volatility_percent, buy_count, buy_thresh, sell_count, sell_thresh, volume_check, \
            price_direction, minute_15_percent_change

    def select_asset(self, time_frame):
        volatility_list = []
        buy_counts = []
        sell_counts = []
        buy_thresh = []
        sell_thresh = []
        direction_list = []
        direction_percent_list = []
        tickers = self.ticker.copy()  # copy ticker list without modifying it globally
        index = -1
        volatility_set = dict.fromkeys(self.ticker, [])  # untested but should produce same as above but generalized

        for asset in self.ticker:  # analyze previous 24hour performance of all assets on ticker list and pick best one
            try:
                index += 1
                volatility, buys, sells, buy_prices, sell_prices, volume, direction, change_15_min = self.asset_analysis(asset, time_frame)

                if volume != 0:
                    volatility_list.append(volatility)
                    buy_counts.append(buys)
                    sell_counts.append(sells)
                    buy_thresh.append(buy_prices)
                    sell_thresh.append(sell_prices)
                    direction_list.append(direction)
                    direction_percent_list.append(change_15_min)

                    volatility_set[asset].append(f"{volatility:.3f}")

            except:
                print(f"Error getting data for {asset}")
                tickers.pop(index)

        print(f"Available tickers: {tickers}")
        print(f"Volatility: {volatility_list}")
        print(f"15 minute movement percentage: {direction_percent_list}")
        print(f"Price movement: {direction_list}")

        search = 1
        for i in range(len(tickers)):
            next_asset = sorted(volatility_list)[-search]  # sorts volatility list and looks at largest to smallest
            next_asset_index = volatility_list.index(next_asset)  # finds index in volatility list according to value
            if direction_list[next_asset_index] == "Rising":  # checks if volatility corresponds with rising value
                self.current_asset = tickers[next_asset_index]  # selects current asset since it's volatile and rising
                self.current_asset_direction = direction_list[next_asset_index]
                self.current_asset_15min_percentage = direction_percent_list[next_asset_index]
                self.buy_thresh = buy_thresh[next_asset_index]
                self.sell_thresh = sell_thresh[next_asset_index]
                print(f"Chosen asset: {self.current_asset}")
                print(f"Chosen asset direction: {self.current_asset_direction}")
                print(f"Chosen asset 15 min movement: {self.current_asset_15min_percentage:.4f}%")
                break
            search += 1


    def test(self):
        data = yf.download(tickers=self.ticker, period="60m", interval="1m")  # get data of all assets
        print(data)
        self.select_asset("60m")


    def historical(self, profit_sell_thresh, loss_sell_thresh, period_start, period_end):  # used to test strategies on historical data
        profit_sell = profit_sell_thresh  # these are the values to be optimized
        loss_sell = loss_sell_thresh  # these are the values to be optimized
        start = period_start  # start date of analysis
        end = period_end  # end date of analysis

        data = yf.download(tickers=self.ticker, start=start, end=end, interval="1m")  # use self.ticker in production

        data_frame = pd.DataFrame(index=data.index, columns=self.ticker)
        data_frame.drop(index=data_frame.index[:60], inplace=True)  # remove first 60 rows since this will store 60m volatility

        print("Analyzing volatility...")
        for row in range(len(data["Close"]) - 60):
            for col in range(len(self.ticker)):
                prev_60_price = data['Close'][self.ticker[col]][row:60 + row]
                prev_60_volume = data['Volume'][self.ticker[col]][row:60 + row]

                max_price = max(prev_60_price)  # largest price in last 60 mins
                min_price = min(prev_60_price)  # smallest price in last 60 mins
                avg_price = sum(prev_60_price) / len(prev_60_price)  # average price of last 60 mins
                volume_check = sum(prev_60_volume)  # to make sure volume is not 0

                thresh = 0.9  # looking to buy/sell within % of 24 hour historical low/high price
                sell_thresh = (max_price - avg_price) * thresh + avg_price
                buy_thresh = (avg_price - min_price) * (1 - thresh) + min_price
                threshed_volatility = sell_thresh - buy_thresh  # comparing difference between buy and sell points

                # determine most volatile asset  (value is % change over last 60 mins from potential buy/sell points)
                volatility = (1 - ((buy_thresh - threshed_volatility) / buy_thresh)) * 100

                if volume_check != 0:
                    data_frame.loc[data_frame.index[row], self.ticker[col]] = volatility
                else:
                    volatility = 0
                    data_frame.loc[data_frame.index[row], self.ticker[col]] = volatility


        # main loop starts here once volatility for time period has been analyzed
        prev_asset = "Not equal to current_asset"
        print(f"Starting price analysis for {profit_sell}% profit sell, {loss_sell}% loss sell from {start} to {end}.")

        for i in range(len(data_frame) - 60):
            index = i
            row_volatility_data = data_frame.loc[[data_frame.index[index]]]  # returns all values at given row index
            max_volatility = row_volatility_data.max(axis=1)[0]  # returns largest value without timestamp,[0] selects value only

            if self.quantity == 0:
                try:
                    self.current_asset = data_frame.columns[(data_frame == max_volatility).iloc[index]][0]  # returns column name with highest value
                except:
                    self.current_asset = "None"  # used when no options are available to prevent crashing

            if self.current_asset != prev_asset:
                isolated_data = yf.download(tickers=self.current_asset, start=start, end=end, interval="1m")
                prev_asset = self.current_asset

            try:
                prev_previous_price = isolated_data['Close'][58 + i]
                previous_price = isolated_data['Close'][59 + i]
                current_price = isolated_data['Close'][60 + i]
                time_stamp = isolated_data.index[60 + i]  # time stamp associated with current price
            except:
                prev_previous_price = 0
                previous_price = 0
                current_price = 0
                time_stamp = 0

            if self.purchase_price != 0:
                percent_delta = (current_price - self.purchase_price) * 100 / self.purchase_price  # percent change in price since purchase
            else:
                percent_delta = 0

            # sell asset for a profit
            if (percent_delta > profit_sell) and (current_price < previous_price) and (self.quantity > 0):
                # print(f"Profit sell -> Percent delta: {percent_delta}%")
                self.profit_sell_count += 1
                self.historical_sell_asset(self.current_asset, current_price, time_stamp)
                continue

            # price is falling so take the loss and try again when conditions are more favorable
            if (self.quantity > 0) and (percent_delta < loss_sell):
                # print(f"Loss sell -> Percent delta: {percent_delta}%")
                self.loss_sell_count += 1
                self.historical_sell_asset(self.current_asset, current_price, time_stamp)
                continue

            # buy asset since price is continuously rising
            if (current_price > previous_price) and (previous_price > prev_previous_price) and (self.quantity == 0):
                self.historical_buy_asset(self.current_asset, current_price)

            if self.quantity == 0:  # re-evaluate every loop if nothing purchased
                continue

            print(f"{i}/{len(data_frame) - 60} iterations complete.")

        if self.bankroll == 0:
            print(
                f"Total trades: {self.profit_sell_count + self.loss_sell_count}, "
                f"Profit Sells: {self.profit_sell_count},"
                f" Loss Sells: {self.loss_sell_count}, Net Value: ${self.quantity * current_price:.2f}," 
                f" Total Fees: ${self.fee_total:.2f}")
        else:
            print(f"Total Trades: {self.profit_sell_count+self.loss_sell_count}, Profit Sells: {self.profit_sell_count},"
                  f" Loss Sells: {self.loss_sell_count}, Net Value: ${self.bankroll:.2f}, Total Fees: ${self.fee_total:.2f}")

        self.transaction_table.to_excel(f"{working_directory}\\auto_trader_historical_calibration_{profit_sell}_{loss_sell}_{self.loop_fee*100}.xlsx",
                                        sheet_name=f'{profit_sell}%_{loss_sell}%_{self.loop_fee*100}%', index=False, header=True)
        print(f"File saved to {working_directory}/auto_trader_historical_calibration_{profit_sell}_{loss_sell}_{self.loop_fee*100}.xlsx")

        if self.bankroll == 0:
            net_value = self.quantity * current_price
        else:
            net_value = self.bankroll

        return self.profit_sell_count, self.loss_sell_count, net_value, self.fee_total

    def historical_buy_asset(self, ticker, price):
        self.purchase_price = price
        prev_bankroll = self.bankroll
        self.bankroll = self.bankroll*self.swap_fee
        self.fee_total += prev_bankroll - self.bankroll
        # print(f"Buying power: ${self.bankroll}")
        self.quantity = self.bankroll/self.purchase_price
        self.asset_owned = f'{ticker}'
        self.bankroll = 0.0
        # print(f"Purchased {self.quantity} {self.asset_owned} \t Total fees: ${self.fee_total:.2f}")
        self.buy_count += 1

    def historical_sell_asset(self, ticker, price, time_stamp):
        self.sell_price = price
        prev_bankroll = self.sell_price*self.quantity
        self.bankroll = self.sell_price*self.quantity*self.swap_fee
        self.fee_total += prev_bankroll - self.bankroll
        self.transaction_history += [[time_stamp, self.current_asset, self.purchase_price,
                                     self.sell_price, self.quantity, self.sell_price*self.quantity*self.swap_fee -
                                     self.purchase_price*self.quantity*self.swap_fee,
                                     self.sell_price*self.quantity*self.swap_fee,
                                     self.profit_sell_count+self.loss_sell_count, self.fee_total]]

        self.transaction_table = pd.DataFrame(self.transaction_history,
                                              columns=["Date/Time", "Ticker", "Purchase Price ($)",
                                                       "Sell Price ($)", "Quantity", "Profit ($)",
                                                       "Total Value ($)", "Trade Number", "Total Fees ($)"])
        self.quantity = 0
        self.purchase_price = 0.0
        self.asset_owned = "None"
        self.sell_count += 1

    def calibration(self, profit_max, profit_min, loss_max, loss_min, step_size, start, end):
        print("Selling threshold calibration starting...")

        profit_iterations = int((profit_max - profit_min)/step_size)
        loss_iterations = int(abs((loss_max - loss_min)/step_size))
        total_iterations = profit_iterations*loss_iterations
        iteration = 0
        # print(f"profit: {profit_iterations}, loss: {loss_iterations}, total: {total_iterations}")
        results = []

        start_time = start
        end_time = end

        for profit in range(profit_iterations):
            for loss in range(loss_iterations):
                self.bankroll = 1000.0
                self.fee_total = 0.0
                self.quantity = 0
                self.purchase_price = 0.0
                self.profit_sell_count = 0
                self.loss_sell_count = 0
                iteration += 1
                print(f"Iteration: {iteration}/{total_iterations}")
                profit_sells, loss_sells, value, fees = self.historical(profit*step_size + 0.5, -loss*step_size, start_time, end_time) # analyze ticker prices over a week (within last 30 days)
                total_trades = profit_sells + loss_sells
                print(f"Value: {value}")

                results += [[total_trades, profit_sells, loss_sells, value, fees, profit*step_size + profit_min, -loss*step_size + loss_min]]
                results_table = pd.DataFrame(results, columns=["Total Trades", "Profit Sells", "Loss Sells",
                                                           "Net Value ($)", "Total Fees ($)", "Profit Thresh (%)",
                                                           "Sell Thresh (%)"])

                if iteration % 50 == 0:  # log results after every 50 iterations
                    max_value = max(results_table["Net Value ($)"])
                    calibrated_result = results_table.loc[results_table["Net Value ($)"] == max_value]
                    print("Current Optimized Result:")
                    print(calibrated_result)
                    results_table = results_table.append(calibrated_result)  # add best result to bottom of table
                    results_table.to_excel(f"{working_directory}\\auto_trader_sell_thresh_calibration.xlsx",
                                           sheet_name=f'Threshold Calibration', index=False, header=True)
                    print(f"File saved to {working_directory}/auto_trader_sell_thresh_calibration.xlsx")

        max_value = max(results_table["Net Value ($)"])
        calibrated_result = results_table.loc[results_table["Net Value ($)"] == max_value]
        print("Optimized Result:")
        print(calibrated_result)
        results_table = results_table.append(calibrated_result)  # add best result to bottom of table for easy viewing

        results_table.to_excel(f"{working_directory}\\auto_trader_sell_thresh_calibration.xlsx",
                                  sheet_name=f'Threshold Calibration', index=False, header=True)
        print(f"File saved to {working_directory}/auto_trader_sell_thresh_calibration.xlsx")

    def main(self):  # Used to run on real-time data

        self.select_asset("24h")

        daily_timer = time.time()  # reset every 24 hours re-analyze assets' daily performance
        while True:
            start = time.time()
            try:
                data = yf.download(tickers=self.current_asset, period="15m", interval="1m")  # ~3 minutes behind real time data
                prev_previous_price = data['Close'][-3]
                previous_price = data['Close'][-2]
                current_price = data['Close'][-1]
            except:
                previous_price = 0
                current_price = 0
                prev_previous_price = 0
                print("Error getting data or no viable assets.")

            price_delta = current_price - previous_price
            if self.purchase_price != 0:
                percent_delta = (current_price - self.purchase_price)*100/self.purchase_price  # percent change in price since purchase
            else:
                percent_delta = 0

            # status update
            time_stamp = str(datetime.datetime.now())
            time_stamp = time_stamp[:19]
            print(f"Current time: {time_stamp} \t Start time: {self.initialized_time}")
            print(f"Current targeted asset: {self.current_asset}")
            print(f"Current value of holdings  -  Assets: {self.quantity} of {self.current_asset} worth ${self.quantity * current_price:.2f}  \t Bankroll: ${self.bankroll}")
            print(f'Purchase price: ${self.purchase_price:.6f}\tPrevious price: ${previous_price:.6f}\tCurrent price: ${current_price:.6f}')
            print(f'Change in price over the last minute: ${price_delta:.6f}')
            print(f"Percentage gain since purchase: {percent_delta:.4f}%")
            print(f"Value gain since purchase: ${current_price*self.quantity - self.purchase_price*self.quantity:.6f}")
            print(f"Total trading fees: ${self.fee_total:.2f}")
            print(f"Trades completed  -  Buys: {self.buy_count} \t Sells: {self.sell_count} (Profit sells: {self.profit_sell_count}, Loss sells: {self.loss_sell_count})")
            print(self.transaction_table)

            # sell asset for profit
            if (percent_delta > self.profit_sell_thresh) and (current_price < previous_price) and (self.quantity > 0):
                try:
                    self.profit_sell_count += 1
                    self.save_signal += 1
                    self.sell_asset(self.current_asset)
                    self.select_asset("60m")
                except:
                    print("Error selling asset for profit.")

            # sell asset for loss
            if (self.quantity > 0) and (percent_delta < self.loss_sell_thresh):  # loss_sell_thresh = -0.5
                try:
                    self.loss_sell_count += 1
                    self.save_signal += 1
                    self.sell_asset(self.current_asset)
                    self.select_asset("60m")
                except:
                    print("Error selling asset for loss.")

            try:  # buying strategy
                if (current_price > previous_price) and (previous_price > prev_previous_price) and (self.quantity == 0) and (self.current_asset_direction == "Rising"):
                    self.buy_asset(self.current_asset)
                    # keep track of when a buy is above previous sell indicating that it should have been held
            except:
                print("Error in buy indicator")

            if self.quantity == 0:  # re-evaluate every loop if nothing purchased
                try:
                    self.select_asset("60m")
                except:
                    print("Error selecting asset.")

            while time.time() - start < 60:  # data can only be updated once per minute so wait here for fresh data
                time.sleep(0.1)

            if time.time() - daily_timer > daily_timer:  # 24hour cycle complete so re-analyze all assets over last 24hrs
                self.select_asset("24h")
                daily_timer = time.time()  # reset every 24 hours to re-analyze assets daily


if __name__ == '__main__':
    bot = TradingBot()
    bot.main()  # use to run main program
    # bot.test()  # use to test new concepts
    # bot.calibration(4.0, 0.6, -4.0, 0.0, 0.1, "2023-01-20", "2023-01-27")  # use when calibrating selling thresholds for use in main() (max_prof_thresh, min_prof_thresh, max_loss_thresh, min_loss_thresh, step_size, start_date, end_date)




