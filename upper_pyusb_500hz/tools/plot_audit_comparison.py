"""Scientific plots for the two-session CH12 and value-update audit."""
from pathlib import Path
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager

host = Path(__file__).resolve().parents[1]
out = host/'reports/firmware_hardware_audit_20260910'
font_manager.fontManager.addfont('C:/Windows/Fonts/msyh.ttc')
plt.rcParams.update({'font.family': 'Microsoft YaHei', 'axes.unicode_minus': False,
                     'font.size': 12, 'axes.spines.top': False, 'axes.spines.right': False,
                     'path.simplify': False})
old = np.load(host/'reports/press_plot_20260910_run01/plots/left12_data.npz')
new = np.load(host/'reports/long_set_comparison_20260910_run01/plots/right12_data.npz')
fig, axes = plt.subplots(2, 1, figsize=(13, 8))
for ax, data, title, color in [(axes[0], old, '原左12点板 CH12 · 跨度 40', '#af7a19'),
                              (axes[1], new, '新接整套中的右12点板 CH12 · 跨度 335,759', '#266c94')]:
    ax.plot(data['host_elapsed_s'], data['delta'][:, 11], lw=.8, color=color)
    ax.set_title(title, loc='left', fontsize=15)
    ax.set_ylabel('相对参考基线 / 码值')
    ax.set_xlabel('各自录制的主机接收相对时间 / s')
    ax.grid(axis='y', color='#e4e8eb')
    ax.ticklabel_format(axis='y', style='plain', useOffset=False)
fig.suptitle('CH12：换整套前后对照', x=.12, ha='left', fontsize=21)
fig.text(.12,.012,'两次手动加载，力与位置未同步标定；纵轴独立，跨度比不能当作灵敏度比。全部帧直接绘制。',fontsize=11)
fig.tight_layout(rect=(0,.04,1,.95),h_pad=2)
fig.savefig(out/'ch12_comparison.png', dpi=160)
fig.savefig(out/'ch12_comparison.svg')
plt.close(fig)

# Illustrate a steep part of the new CH12 trace, retaining every received frame.
t = new['host_elapsed_s']; x = new['pressure'][:,11]
active = (t>=38)&(t<=46)
indices = np.flatnonzero(active)
center = indices[np.argmax(np.abs(np.diff(x[active], prepend=x[active][0])))]
start = max(0,center-25); stop = min(len(t),center+26)
changed = np.flatnonzero(np.diff(x[active]) != 0)+1
intervals = np.diff(changed)
values, counts = np.unique(intervals, return_counts=True)
stats = {'window_host_seconds': [38,46], 'changed_values': len(changed),
         'changed_values_per_second': len(changed)/(t[active][-1]-t[active][0]),
         'interval_frame_counts': dict(zip(map(str,values.tolist()),counts.tolist())),
         'four_or_five_frame_fraction': float(np.mean((intervals==4)|(intervals==5))),
         'zoom_host_seconds': [float(t[start]),float(t[stop-1])],
         'interpretation': 'Observable quantized register-value updates, not DRDY-confirmed ADC conversion count.'}
fig, axes = plt.subplots(1,2,figsize=(14,5),gridspec_kw={'width_ratios':[1.65,1]})
axes[0].plot((t[start:stop]-t[start])*1000,x[start:stop], 'o-', ms=4,lw=1,color='#266c94')
axes[0].set_title('新右12点板 CH12：每个圆点是一帧',loc='left',fontsize=14)
axes[0].set_xlabel('局部主机接收时间 / ms');axes[0].set_ylabel('传输压力码值')
axes[0].ticklabel_format(axis='y',style='plain',useOffset=False)
axes[1].bar(values,counts,color='#266c94')
axes[1].set_title('38～46秒内：相邻数值变化的帧间隔',loc='left',fontsize=13)
axes[1].set_xlabel('间隔帧数（每帧约2 ms）');axes[1].set_ylabel('次数')
axes[1].set_xticks(values)
for ax in axes:ax.grid(axis='y',color='#e4e8eb');ax.set_axisbelow(True)
fig.suptitle('500帧/秒 ≠ 500次/秒新测量', x=.08,ha='left',fontsize=21)
fig.text(.08,.015,'数据点未平滑、未抽样；本图统计码值变化，不能替代芯片 DRDY 或转换完成时序验证。',fontsize=11)
fig.tight_layout(rect=(0,.06,1,.92))
fig.savefig(out/'frame_vs_value_updates.png',dpi=160)
fig.savefig(out/'frame_vs_value_updates.svg')
plt.close(fig)
(out/'update_timing_audit.json').write_text(json.dumps(stats,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(stats,ensure_ascii=False))
