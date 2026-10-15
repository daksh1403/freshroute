"""Local Streamlit dashboard. Every figure comes from the independent evaluator."""
from dataclasses import asdict
import json
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from freshroute.model import Scenario, ValidationError
from freshroute.io import load_scenario, report_zip, csv_text
from freshroute.engine import baseline, optimize
from freshroute.evaluation import evaluate, compare
from freshroute.insights import shipment_rows, explain, discounts
from freshroute.scenario import change_scenario, replan

st.set_page_config(page_title='FreshRoute | Dispatch intelligence',page_icon='🌱',layout='wide')
st.markdown('''<style>
.block-container {max-width:1440px;padding-top:2rem}
h1,h2,h3 {letter-spacing:-.035em}
[data-testid="stMetric"] {background:white;border:1px solid #dfE8e7;border-radius:12px;padding:18px}
[data-testid="stMetricLabel"] {color:#647a88}
footer{visibility:hidden}
</style>''',unsafe_allow_html=True)

st.caption('FRESHROUTE  /  OPERATIONS WORKSPACE')
st.title('Good produce. Better decisions.')
st.write('Allocate stock while it is fresh. See the economics behind every dispatch.')

with st.sidebar:
    st.header('Planning inputs')
    st.caption('Synthetic demo supplied. Replace it with your own scenario.')
    upload = st.file_uploader('Import JSON or Excel scenario',type=['json','xlsx'])
    st.caption('CSV directories are supported through the command line. Input contract: README.md.')
    limit = st.number_input('Solver time limit (seconds)',min_value=1,max_value=60,value=15)
try:
    original = load_scenario(upload.getvalue(),format='xlsx' if upload and upload.name.endswith('.xlsx') else 'json') if upload else load_scenario(Path(__file__).parent/'examples/demo')
except ValidationError as exc:
    st.error(str(exc)); st.stop()
with st.sidebar:
    horizon = st.number_input('Planning horizon (hours)',min_value=0.1,value=float(original.config.horizon_hours))
    handling = st.number_input('Handling time (hours)',min_value=0.0,value=float(original.config.handling_hours))
    st.info('Planning sandbox: shipments have not been committed or dispatched. Submit residual stock for live replanning.')
raw = original.to_dict(); raw['config']['horizon_hours']=horizon; raw['config']['handling_hours']=handling
s = Scenario.from_dict(raw)
fingerprint = json.dumps(s.to_dict(),sort_keys=True)
if st.session_state.get('fingerprint') != fingerprint:
    for key in ('result','disruption'): st.session_state.pop(key,None)
    st.session_state.fingerprint=fingerprint

st.caption(f'{s.config.label}  ·  {horizon:g} hour horizon  ·  {s.config.quantity_unit}  ·  {s.config.currency}  ·  sales on arrival')
if st.button('Generate optimized plan',type='primary',key='generate'):
    with st.spinner('Solving allocation and checking every constraint…'):
        st.session_state.result=(baseline(s),optimize(s,float(limit)))
        st.session_state.pop('disruption',None)

if 'result' not in st.session_state:
    st.info('Generate a plan to run the baseline and optimizer on identical inputs.')
    st.dataframe(pd.DataFrame([asdict(b) for b in s.inventory]),hide_index=True,width='stretch')
    with st.expander('Inspect demand and transport'):
        st.dataframe(pd.DataFrame([asdict(d) for d in s.demand]),hide_index=True)
        st.dataframe(pd.DataFrame([asdict(r) for r in s.routes]),hide_index=True)
    st.stop()
b,p = st.session_state.result
mb,mp=evaluate(s,b),evaluate(s,p)
currency=s.config.currency
cols=st.columns(4)
cols[0].metric(f'Optimized net revenue · {currency}',f"{mp['net_revenue']:,.2f}",f"{mp['net_revenue']-mb['net_revenue']:+,.2f} vs FEFO")
cols[1].metric('Demand fulfilled',f"{mp['demand_fulfillment_percent']:.1f}%")
cols[2].metric(f'Spoilage by horizon · {s.config.quantity_unit}',f"{mp['spoiled_quantity']:,.1f}",f"{mp['spoiled_quantity']-mb['spoiled_quantity']:+,.1f} vs FEFO",delta_color='inverse')
cols[3].metric('Constraint violations',str(len(mp['constraint_violations'])))
if mp['constraint_violations']: st.error(mp['constraint_violations'])
else: st.success(f'Independently validated · solver status: {p.status} · {p.runtime_seconds:.3f}s · gap: {p.mip_gap if p.mip_gap is not None else "not supplied"}')
if p.status != 'optimal': st.warning(p.message)
if mp['spoiled_quantity'] > mb['spoiled_quantity'] + 1e-6:
    st.warning(f"Economic trade-off: this plan leaves {mp['spoiled_quantity']-mb['spoiled_quantity']:g} {s.config.quantity_unit} more spoilage than FEFO under the supplied disposal penalties. Inspect the full comparison before dispatch.")

plan_tab,comparison_tab,inventory_tab,insights_tab,disruption_tab,reports_tab=st.tabs(['Dispatch plan','Baseline comparison','Inventory & inputs','Decision evidence','Disruption sandbox','Reports'])
with plan_tab:
    st.subheader('The next dispatch wave')
    rows=shipment_rows(s,p)
    if rows:
        st.dataframe(pd.DataFrame(rows),hide_index=True,width='stretch')
        fig=px.bar(pd.DataFrame(rows),x='destination_id',y='quantity',color='commodity',color_discrete_sequence=['#087f5b','#e7b641','#5c87b9'],labels={'quantity':s.config.quantity_unit,'destination_id':'Destination'})
        fig.update_layout(plot_bgcolor='white',paper_bgcolor='rgba(0,0,0,0)',legend_title_text='Commodity',margin=dict(l=0,r=0,t=15,b=0))
        st.plotly_chart(fig,width='stretch')
    else: st.info('No feasible economically beneficial dispatch selected. Inspect the decision evidence.')
    st.caption('Dispatch priority sorts the selected loads by expiry. All shipments leave in the same planning wave.')
with comparison_tab:
    st.subheader('A fair comparison on the same inputs')
    st.caption('FEFO baseline: earliest expiry first, then best feasible current contribution. Percentage change is undefined when baseline is zero.')
    table=[{'metric':key,**v} for key,v in compare(s,b,p).items()]
    st.dataframe(pd.DataFrame(table),hide_index=True,width='stretch')
    st.subheader('Baseline shipments')
    st.dataframe(pd.DataFrame(shipment_rows(s,b)),hide_index=True,width='stretch')
with inventory_tab:
    st.subheader('Inventory and operational constraints')
    used={batch.batch_id:sum(x.quantity for x in p.shipments if x.batch_id==batch.batch_id) for batch in s.inventory}
    st.dataframe(pd.DataFrame([{**asdict(batch),'shipped_quantity':used[batch.batch_id], 'unshipped_quantity':batch.quantity-used[batch.batch_id],
                               'risk':'Expires by horizon' if batch.shelf_life_hours<=horizon else 'Survives horizon'} for batch in s.inventory]),hide_index=True)
    for name in ('demand','routes','resources'):
        st.write(name.capitalize()); st.dataframe(pd.DataFrame([asdict(v) for v in getattr(s,name)]),hide_index=True,width='stretch')
with insights_tab:
    evidence=explain(s,p)
    st.subheader('Why these shipments?')
    for row in evidence['shipments']:
        with st.expander(f"{row['batch_id']} → {row['destination_id']} · {row['quantity']:g} {s.config.quantity_unit}"):
            st.write(row['reason'])
    st.write('Remaining stock'); st.dataframe(pd.DataFrame(evidence['remaining_inventory']),hide_index=True)
    st.write('Rejected batch / route combinations'); st.dataframe(pd.DataFrame(evidence['rejected_allocations']),hide_index=True)
    st.write('Capacity, inventory and demand checks'); st.dataframe(pd.DataFrame(evidence['constraint_utilization']),hide_index=True)
    st.subheader('Markdown scenarios')
    st.caption('Demand response is unverified. These suggestions do not add customers or revenue to the plan.')
    markdowns=discounts(s,p)
    if markdowns: st.dataframe(pd.DataFrame(markdowns),hide_index=True,width='stretch')
    else: st.info('No unshipped stock expires within this horizon.')
with disruption_tab:
    st.subheader('Conditions change. Recalculate the plan.')
    st.caption('Unexecuted planning sandbox. Reductions apply to route and shared resource capacities. The previous plan is checked under the new constraints.')
    route=st.selectbox('Delay affects route',['All routes']+[r.route_id for r in s.routes])
    c1,c2,c3=st.columns(3)
    delay=c1.slider('Additional travel hours',0.0,48.0,0.0,0.5,key='delay')
    capacity=c2.slider('Available capacity (%)',0,150,100)
    demand=c3.slider('Destination demand (%)',0,200,100)
    c4,c5=st.columns(2)
    price=c4.slider('Selling prices (%)',0,200,100)
    inventory=c5.slider('Inventory available (%)',0,150,100)
    if st.button('Replan with disruption',key='replan'):
        updated=change_scenario(s,delay_hours=delay,capacity_factor=capacity/100,demand_factor=demand/100,price_factor=price/100,inventory_factor=inventory/100,route_id=None if route=='All routes' else route)
        with st.spinner('Revalidating conditions and optimizing…'): result=replan(s,p,updated,float(limit))
        st.session_state.disruption=(updated,result)
    if 'disruption' in st.session_state:
        updated,result=st.session_state.disruption
        if not result['previous_plan_feasible']:
            st.warning('Previous plan is infeasible under the updated conditions. Its revenue is not a feasible benchmark.')
            st.write(result['previous_plan_violations'])
        else: st.success('Previous plan remains feasible under the updated conditions.')
        st.write('Updated optimized metrics'); st.json(result['updated_metrics'])
        st.write('Allocation changes'); st.dataframe(pd.DataFrame(result['changes']),hide_index=True)
        st.write('Updated shipments'); st.dataframe(pd.DataFrame(shipment_rows(updated,result['plan'])),hide_index=True)
        st.download_button('Download disruption report',report_zip(updated,baseline(updated),result['plan']),'freshroute-disruption.zip','application/zip')
with reports_tab:
    st.subheader('Take the evidence with you')
    st.download_button('Download complete report',report_zip(s,b,p),'freshroute-report.zip','application/zip')
    st.download_button('Download shipments CSV',csv_text(shipment_rows(s,p)),'freshroute-shipments.csv','text/csv')
    st.download_button('Download current scenario',json.dumps(s.to_dict(),indent=2),'freshroute-scenario.json','application/json')
    st.caption('Report includes source scenario, baseline, optimized plan, independent metrics, constraints, explanations, and unverified markdown scenarios.')
    with st.expander('Assumptions and solver metadata'):
        st.json({'config':asdict(s.config),'status':p.status,'primary_objective':p.primary_objective,'secondary_status':p.secondary_status,'gap':p.mip_gap,'message':p.message})
        st.write('Immediate sale on arrival. Optional costs absent in imports are zero. Shared resource capacity is a quantity budget per planning wave. Unsold stock only spoils when it expires within the horizon. See README for complete input contract and limitations.')
