# 마지막 거래의 PnL계산
def cal_pnl(ledger):
    # Initialize variables to store accumulated out and in amounts
    accumulated_out = 0
    accumulated_in = 0
    is_out_active = False
    total_pnl = 0

    # Iterate over the data
    for entry in ledger:
        if entry['direction'] == 'out':
            # If 'out' is active, accumulate the amounts
            accumulated_out += entry['amount']
            is_out_active = True  # Set flag to indicate we are in an "out" phase
        elif entry['direction'] == 'in' and is_out_active:
            # Accumulate 'in' amounts once 'out' phase is active
            accumulated_in += entry['amount']
            
            # After the last 'in' (when 'in' series ends), calculate PnL for the whole trade
            if entry == ledger[-1] or ledger[ledger.index(entry) + 1]['direction'] == 'out':
                # Calculate PnL for this trade
                pnl = accumulated_in - accumulated_out
                total_pnl += pnl
                # Reset accumulators for the next trade
                accumulated_out = 0
                accumulated_in = 0
                is_out_active = False  # Reset the flag for the next series

    # The result is the total PnL of all matched trades
    final_result = total_pnl

    return final_result