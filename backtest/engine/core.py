"""Deterministic, bar-based backtest engine. Signals at close fill only next open."""
import math
from statistics import mean, pstdev
from backtest.strategies.registry import get_strategy_logic

def atr(bars, index, period):
    if index < period: return None
    trs=[]
    for i in range(index-period+1, index+1):
        prev=bars[i-1]["close"] if i else bars[i]["close"]
        trs.append(max(bars[i]["high"]-bars[i]["low"], abs(bars[i]["high"]-prev), abs(bars[i]["low"]-prev)))
    return mean(trs)

def _fill(price, side, bps): return price * (1 + (bps / 10000 if side == "buy" else -bps / 10000))

def run(strategy, bars, *, evaluation_start=0, evaluation_end=None):
    e, x, r, ex = strategy["entry"], strategy["exit"], strategy["risk"], strategy["execution"]
    signal_logic = get_strategy_logic(strategy)
    minimum = max(signal_logic.minimum_history(strategy), x["atr_period"]) + 2
    if len(bars) < minimum:
        raise ValueError(f"insufficient history: need at least {minimum} bars")
    evaluation_end = len(bars) - 1 if evaluation_end is None else evaluation_end
    if not 0 <= evaluation_start <= evaluation_end < len(bars):
        raise ValueError("invalid evaluation boundaries")
    equity=r["initial_equity"]; cash=equity; position=None; pending=None; pending_exit=None; trades=[]; curve=[]; commissions=slippage=0.0
    # State starts flat at the active boundary. Earlier bars remain readable by
    # indicator functions but are never traversed for signals, fills, or P&L.
    for i in range(evaluation_start, evaluation_end + 1):
        bar = bars[i]
        exited_this_bar = False
        if pending_exit == i and position is not None:
            long=position["side"]=="long"; raw=bar["open"]; fill=_fill(raw,"sell" if long else "buy",ex["slippage_bps"])
            pnl=(fill-position["entry"])*position["qty"]*(1 if long else -1); commission=ex["commission_per_trade"]; cash+=pnl-commission; equity=cash; commissions+=commission; slippage+=abs(fill-raw)*position["qty"]
            trades.append({"signal_time":position["signal_time"],"entry_time":position["entry_time"],"exit_time":bar["timestamp"],"side":position["side"],"quantity":position["qty"],"entry_price":position["entry"],"exit_price":fill,"exit_reason":"strategy_exit","pnl":pnl-(2*commission),"commission":2*ex["commission_per_trade"]}); position=None; pending_exit=None; exited_this_bar=True
        # execute only the order scheduled from the previous completed bar.
        if pending and pending["execute_index"] == i and position is None:
            raw=bar["open"]; fill=_fill(raw, "buy" if e["direction"]=="long" else "sell", ex["slippage_bps"])
            risk_per_unit=pending["atr"] * x["stop_atr_multiple"]
            qty=max(1, math.floor((equity*r["risk_per_trade_pct"])/risk_per_unit))
            target_multiple=x.get("take_profit_atr_multiple")
            position={"side":e["direction"],"qty":qty,"entry":fill,"entry_time":bar["timestamp"],"signal_time":pending["signal_time"],"stop":fill + (-1 if e["direction"]=="long" else 1)*risk_per_unit,"target":None if target_multiple is None else fill + (1 if e["direction"]=="long" else -1)*pending["atr"]*target_multiple}
            commission=ex["commission_per_trade"]; cash-=commission; commissions+=commission; slippage+=abs(fill-raw)*qty; pending=None
        if position:
            long=position["side"]=="long"; stop_hit=bar["low"]<=position["stop"] if long else bar["high"]>=position["stop"]; target_hit=position["target"] is not None and (bar["high"]>=position["target"] if long else bar["low"]<=position["target"])
            # Conservative assumption: if both occur in one OHLC bar, stop fills first.
            if stop_hit or target_hit:
                raw=position["stop"] if stop_hit else position["target"]; reason="stop" if stop_hit else "take_profit"; fill=_fill(raw, "sell" if long else "buy", ex["slippage_bps"])
                pnl=(fill-position["entry"])*position["qty"]*(1 if long else -1); commission=ex["commission_per_trade"]; cash+=pnl-commission; equity=cash; commissions+=commission; slippage+=abs(fill-raw)*position["qty"]
                trades.append({"signal_time":position["signal_time"],"entry_time":position["entry_time"],"exit_time":bar["timestamp"],"side":position["side"],"quantity":position["qty"],"entry_price":position["entry"],"exit_price":fill,"exit_reason":reason,"pnl":pnl-(2*commission),"commission":2*ex["commission_per_trade"]}); position=None; exited_this_bar = True
        if position is not None and pending_exit is None and i + 1 <= evaluation_end:
            exit_logic=getattr(signal_logic,"evaluate_exit",None)
            if exit_logic and exit_logic(strategy,bars,i,position): pending_exit=i+1
        # Strategy logic only evaluates the close signal. The shared engine owns all state and execution.
        if position is None and pending is None and not exited_this_bar and i >= max(signal_logic.minimum_history(strategy), x["atr_period"]):
            a=atr(bars,i,x["atr_period"])
            signal=signal_logic.evaluate_entry(strategy,bars,i)
            if signal and i + 1 <= evaluation_end: pending={"execute_index":i+1,"atr":a,"signal_time":bar["timestamp"]}
        marked= cash if not position else cash + (bar["close"]-position["entry"])*position["qty"]*(1 if position["side"]=="long" else -1)
        curve.append({"timestamp":bar["timestamp"],"equity":marked})
    return {"trades":trades,"equity_curve":curve,"commission":commissions,"slippage":slippage}

def metrics(result, initial):
    trades=result["trades"]; pnls=[t["pnl"] for t in trades]; final=result["equity_curve"][-1]["equity"]; wins=[p for p in pnls if p>0]; losses=[p for p in pnls if p<0]; peak=initial; max_dd=0
    returns=[]; prior=initial
    for p in result["equity_curve"]:
        returns.append((p["equity"]-prior)/prior); prior=p["equity"]; peak=max(peak,p["equity"]); max_dd=max(max_dd,(peak-p["equity"])/peak)
    sd=pstdev(returns) if len(returns)>1 else 0; downside=[min(0,v) for v in returns]; dsd=math.sqrt(mean([v*v for v in downside])) if downside else 0
    years=max(1/252,len(result["equity_curve"])/252)
    return {"trades":len(trades),"win_rate":len(wins)/len(trades) if trades else 0,"avg_win":mean(wins) if wins else 0,"avg_loss":mean(losses) if losses else 0,"profit_factor":sum(wins)/abs(sum(losses)) if losses else None,"expectancy":mean(pnls) if pnls else 0,"max_drawdown":max_dd,"sharpe":(mean(returns)/sd*math.sqrt(252)) if sd else 0,"sortino":(mean(returns)/dsd*math.sqrt(252)) if dsd else 0,"total_return":final/initial-1,"cagr":(final/initial)**(1/years)-1,"exposure":sum(1 for p in result["equity_curve"] if p["equity"]!=initial)/len(result["equity_curve"]),"commission":result["commission"],"slippage":result["slippage"]}
