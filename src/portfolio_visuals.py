"""Portable pastel/retro figures from verified frozen forecast artifacts."""
from pathlib import Path
import hashlib,json
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.ticker import FuncFormatter
try:
    from .notebook_display import configure_notebook
except ImportError:
    from notebook_display import configure_notebook
ROOT=Path(__file__).resolve().parents[1]
COLORS={"Action":"#b49aca","Strategy":"#90bba7","RPG":"#d8ac7d","Massively Multiplayer":"#8cb4cb","Indie":"#d69fb5"}

def build(root=ROOT):
    root=Path(root);folder=root/'reports/fixed_cohort_forecast_2027'
    manifest=json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
    required={'annual_summary.csv','monthly_projections.csv','monthly_historical_error_ranges.csv'}
    if not required.issubset(manifest.get('outputs',{})):raise ValueError('Missing verified figure inputs')
    for name,expected in manifest['outputs'].items():
        if hashlib.sha256((folder/name).read_bytes()).hexdigest()!=expected:raise ValueError('Frozen figure source changed')
    policy_path=folder/'frozen_policy.json'
    if hashlib.sha256(policy_path.read_bytes()).hexdigest()!=manifest['policy_sha256']:raise ValueError('Frozen figure policy changed')
    policy=json.loads(policy_path.read_text(encoding='utf-8'))
    if hashlib.sha256((root/'reports/fixed_sources_v2/category_monthly.csv').read_bytes()).hexdigest()!=policy['input_sha256']:raise ValueError('Observed figure source changed')
    annual=pd.read_csv(folder/'annual_summary.csv')
    monthly=pd.read_csv(folder/'monthly_projections.csv',parse_dates=['month'])
    bands=pd.read_csv(folder/'monthly_historical_error_ranges.csv',parse_dates=['month'])
    configure_notebook()
    plt.rcParams.update({'font.family':'DejaVu Sans Mono','svg.hashsalt':'steam-portfolio-v2'})
    out=root/'outputs/final_figures';out.mkdir(parents=True,exist_ok=True)
    paths={}
    def save(fig,name):
        for ext in ['png','svg']:
            fig.savefig(out/f'{name}.{ext}',dpi=160,bbox_inches='tight',metadata={'Date':None} if ext=='svg' else {})
        paths[name]=out/f'{name}.png';plt.close(fig)
    selected=annual.loc[annual.policy.eq('Provisional v2 policy')].sort_values('rank')
    categories=selected.category.tolist();reference=annual.loc[annual.policy.eq('Last-value reference')].set_index('category')
    fig,ax=plt.subplots(figsize=(11,5.8));y=np.arange(5)
    ax.barh(y,selected.projected_mean_activity/1e6,height=.58,color=[COLORS[c] for c in categories],edgecolor='#514b65',linewidth=.8)
    ax.scatter(reference.loc[categories].projected_mean_activity/1e6,y,marker='s',s=70,facecolors='none',edgecolors='#514b65',linewidths=1.4,label='Last-value reference',zorder=3)
    for row,pos in zip(selected.itertuples(),y):ax.text(max(row.projected_mean_activity,reference.loc[row.category,'projected_mean_activity'])/1e6+.055,pos,f'{row.projected_mean_activity:,.0f}',va='center',fontsize=10)
    ax.set(yticks=y,yticklabels=['MMO' if c=='Massively Multiplayer' else c for c in categories],xlim=(0,4.05),xlabel='Projected mean concurrent activity · millions')
    ax.invert_yaxis();ax.set_title('2027 activity · provisional fixed-cohort projection',loc='left',pad=22)
    ax.legend(loc='lower right',frameon=False);ax.grid(axis='x',alpha=.5);ax.set_axisbelow(True)
    fig.text(.02,.015,'519 covered games · Jan 2026 cutoff · overlapping category labels\nBars: selected policy; squares: baseline. Ranking probabilities are unavailable.',fontsize=9,color='#70647e')
    fig.subplots_adjust(left=.16,bottom=.20);save(fig,'annual_comparison')
    observed=pd.read_csv(root/'reports/fixed_sources_v2/category_monthly.csv',parse_dates=['month'])
    fig,axes=plt.subplots(3,2,figsize=(12,10));axes=axes.ravel()
    for ax,category in zip(axes,categories):
        history=observed.loc[observed.category.eq(category)&observed.month.ge('2024-01-01')]
        future=monthly.loc[monthly.category.eq(category)&monthly.policy.eq('Provisional v2 policy')]
        spread=bands.loc[bands.category.eq(category)]
        ax.plot(history.month,history.avg_players,color='#514b65',lw=1.6,drawstyle='steps-mid',label='Observed')
        ax.plot(future.month,future.prediction,color=COLORS[category],lw=2,marker='s',markersize=2.5,drawstyle='steps-mid',label='Projection')
        ax.fill_between(spread.month,spread.historical_error_lower,spread.historical_error_upper,color=COLORS[category],alpha=.25,step='mid',label='Historical-error range')
        ax.axvline(pd.Timestamp('2026-01-01'),color='#81748d',lw=.8,ls='--')
        ax.set_title(category,loc='left');ax.set_ylim(bottom=0);ax.set_xlim(pd.Timestamp('2024-01-01'),pd.Timestamp('2027-12-01'))
        ax.set_xticks(pd.to_datetime(['2024-01-01','2025-01-01','2026-01-01','2027-01-01','2027-12-01']))
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%b\n%Y'));ax.yaxis.set_major_formatter(FuncFormatter(lambda v,p:f'{v/1e6:.1f}m'));ax.grid(alpha=.4)
        ax.tick_params(axis='x',labelsize=8);ax.set_ylabel('Concurrent activity',fontsize=9)
    axes[-1].axis('off');handles,labels=axes[0].get_legend_handles_labels();axes[-1].legend(handles,labels,loc='upper left',frameon=False)
    axes[-1].text(0,.52,'Independent y-axis scales\nMonthly steps retain observations\n\nRanges: dependent historical errors\nNo predictive coverage guarantee\nNo annual confidence interval',transform=axes[-1].transAxes,fontsize=9,va='top',linespacing=1.7)
    fig.suptitle('From recorded activity to the 2027 projection',x=.07,ha='left',fontsize=16,fontweight='bold')
    fig.text(.07,.01,'Fixed 519-game cohort · final training cutoff Jan 2026 · ranges shown for 2027 only',fontsize=10)
    fig.tight_layout(rect=(0,.045,1,.96));save(fig,'forecast_paths')
    return paths

if __name__=='__main__':
    print(build())
