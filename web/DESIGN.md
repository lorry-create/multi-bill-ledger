---
name: 归账
description: 蓝白、沉稳、可核对的个人账务空间
colors:
  primary: "#326fca"
  primary-hover: "#275faf"
  paper: "#f3f7fd"
  surface: "#ffffff"
  text-primary: "#18314f"
  text-secondary: "#627894"
  surface-line: "#dee8f5"
  selected: "#e8f2ff"
  focus: "#6398de"
  placeholder: "#5e738f"
  income: "#397ed8"
  expense: "#91b7e8"
  budget-over: "#c98a43"
  pending-text: "#285fae"
  pending-surface: "#e7f2ff"
typography:
  body:
    fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", "PingFang SC", "Microsoft YaHei", sans-serif'
  display:
    fontSize: "clamp(40px, 4.3vw, 64px)"
    fontWeight: 650
    lineHeight: 1.18
    letterSpacing: "-.035em"
  amount:
    fontSize: "clamp(49px, 5.1vw, 79px)"
    fontWeight: 720
    lineHeight: 1.13
    letterSpacing: "-.035em"
  headline:
    fontSize: "clamp(29px, 3vw, 38px)"
    fontWeight: 740
    lineHeight: 1.25
    letterSpacing: "-.035em"
  title:
    fontSize: "18px"
    fontWeight: 690
    letterSpacing: "-.025em"
  description:
    fontSize: "14px"
    lineHeight: 1.6
  label:
    fontSize: "13px"
    fontWeight: 700
  button:
    fontSize: "13px"
    fontWeight: 620
rounded:
  control: "10px"
  button: "12px"
  login-field: "13px"
  small-panel: "16px"
  panel: "20px"
  dialog: "22px"
  hero: "24px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "12px"
  lg: "16px"
  panel: "24px"
  spacious: "32px"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.surface}"
    typography: "{typography.button}"
    rounded: "{rounded.button}"
    padding: "0 17px"
    height: "43px"
  button-primary-hover:
    backgroundColor: "{colors.primary-hover}"
    textColor: "{colors.surface}"
  button-secondary:
    backgroundColor: "{colors.surface}"
    textColor: "#333338"
    typography: "{typography.button}"
    rounded: "{rounded.button}"
    padding: "0 17px"
    height: "43px"
  login-input:
    backgroundColor: "#fbfdff"
    textColor: "#1d1d1f"
    rounded: "{rounded.login-field}"
    padding: "0 15px"
    height: "50px"
  navigation-active:
    backgroundColor: "#e6f1ff"
    textColor: "#235eb4"
    rounded: "11px"
    padding: "0 13px"
    height: "46px"
  pending-chip:
    backgroundColor: "{colors.pending-surface}"
    textColor: "{colors.pending-text}"
    rounded: "100px"
    padding: "7px 11px"
  report-panel:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.panel}"
    padding: "{spacing.panel}"
  balance-hero:
    textColor: "{colors.text-primary}"
    rounded: "{rounded.hero}"
    padding: "42px 46px"
---

# Design System: 归账

## Overview

**Creative North Star: "清透的个人账本"**

蓝白画布、深蓝正文与系统字体构成沉稳的 iOS 式工作空间。半透明导航和浮层提供轻盈材质，账单、金额与表单保留清楚的对比和阅读顺序。原创归集标记把来源箭头与账本轮廓连成一个记号。

每次进入登录页时，标志的蓝色底层淡出，箭头从左侧进入轮廓。背页从上方、前页从左侧同时滑入，约一秒后一起落定，封面内容随即淡入。右侧表单逐项进入。背景粒子留在左栏。月报的粒子沿数据柱与类别圆环运动。清单按照当前顺序逐条滑入，系统开启减少动态效果时直接显示最终位置。

**Key Characteristics:**

- 浅蓝白底、蓝色行动、深蓝内容。
- 半透明边界与清晰正文并存。
- 金额优先，账单来源和确认状态可辨。
- 动效轻，遵循系统设置，手机任务入口直接可达。

全局样式由 main.css、identity.css、motion.css 和 product.css 提供，navigation.css 定义账本导航。各页在此基础上定义其阅读顺序与信息密度。产品边界见 [PRODUCT.md](PRODUCT.md)。

## Colors

### Primary

归账蓝用于主要操作、选中项、焦点和数字强调；悬停使用更深的行动蓝。蓝色浅底承托当前选择，不代替文字与图形标识。

### Neutral

浅蓝纸面承载工作区，白色面板承载正文；主字深蓝，说明字偏灰蓝，细线划分内容组。占位文字使用独立的可读色。半透明材质只用于导航、流程浮片和反馈层。

### 数据与来源

收入与支出以深浅蓝区分，预算超出另用暖棕，并同时显示名称、金额与超出文字。平台图形保留微信绿与支付宝蓝，仅表达来源，不能被解释为平台合作或自动直连。

**The Content First Rule.** 装饰层不得覆盖文字、吞掉焦点或承担唯一的信息表达；读数和状态必须有可见文本。

## Typography

全站使用前置 token 中的系统字体栈，优先 SF 与苹方。页面标题与金额使用略紧字距，正文保持自然中文节奏，不引入装饰字体。金额用 `tabular-nums` 保持位数变化时对齐。

- **Display**：登录封面的中文月份用宋体，手机收至（40px）。
- **Amount**：收支差额的首要读数；手机通常（48–68px），窄屏为（52px）。
- **Headline / Title**：页面标题与内容分组，层级先于卡片装饰。
- **Description / Label**：页面说明与表单标签；账单正文（13px），图表说明（12px），日期标签（11px）。
- 登录输入为（16px），避免手机聚焦时页面放大。

**The Honest Amount Rule.** 动画金额的辅助技术标签始终读最终值，不能把过渡中的数字当作业务结果。

## Layout

桌面侧栏宽 202px，收起后宽 72px。导入是独立操作，月度报告、全部账单和分类规则是三个主要页面。正文直接从月份或当前任务开始。内容宽度上限为 1460px。

月报以可切换月份为标题。首屏同时呈现收支差额和走势，下方依次显示支出去向、类别预算和收入构成。类别可下钻至当月相应账单，返回后继续阅读该月。

760px 及以下使用顶部品牌与账号区、四项底部导航。内容和操作按钮避让安全区。手机保留可直接操作的导入入口。

桌面登录页左侧保留按月更新的纸质账本封面，右侧留白承载账号和密码。手机把表单放在账本封面之前。

## Elevation & Depth

细分隔线划分日期与报表章节。登录封面用纸页叠层体现深度。浅蓝用于汇总和当前选中项，半透明材质集中在手机导航与浮层。

- 内容面板：`0 16px 40px rgba(35,78,133,.055)`。

- 图表提示：`0 18px 42px rgba(24,54,94,.23)`。
- 编辑弹层：`0 28px 80px rgba(25,25,35,.18)`。

## Shapes

控制项使用紧凑圆角，面板、弹层与主卡依次放大，具体值以前置 token 为准。面板边框细而连续，选中来源保留边框、浅底与单选点三种反馈。状态标签为胶囊；品牌标记采用圆角方形与圆头描边，沿用原创 SVG，不以文字或通用图标替换。

## Components

### Buttons / Inputs

主按钮为蓝底白字，次按钮为白底细边；桌面按钮高（43px），手机至少（44px）。悬停加深，按压轻缩放并出现短暂涟漪，禁用降低透明度并阻止重复触发。键盘焦点为清晰蓝环；输入聚焦加蓝色边框与（4px）浅蓝外晕。

登录字段高（52px），密码提供有明确名称的显示切换。错误在字段附近以文字呈现，等待、锁定倒计时和提交中使用真实状态文案。

### Navigation / Chips / Cards

侧栏选中项用浅蓝底和深蓝字，手机底部导航保留图标与文字，退出入口位于账号旁。

宽屏账本按上海自然日分组，日期、交易、来源和金额各列对齐。点击账单在该行下方展开凭证，可核对来源与已保存字段。窄屏使用底部原生面板，关闭时返回到对应交易。

### 归集封面与品牌

封面展示上海时区的当前年月和微信支付、支付宝两种来源。切换归集、核对和月报时，蓝色选中线随步骤滑动，相应的操作说明轻换入。

归账使用 `public/brand.svg` 原创标记；微信、支付宝使用 `PlatformLogo` 复用真实 SVG 路径，旁边保留平台文字。来源与许可记录在 [public/brands/SOURCES.md](public/brands/SOURCES.md)。

### 图表与金额

环形图支持悬停、键盘聚焦和点击，中心同步当前类别金额与占比；趋势图支持按周、按日查看与选择。桌面提示随指针移动；键盘和手机通过选中状态及固定读数区获取相同数据。零值不绘制假柱，预算超出金额在手机仍显示。

金额变化在（520ms）内收敛，辅助技术直接读最终金额。图表、页面与弹层以短入场连接状态，避免长时间遮挡内容。

账单行从左向右依次进场。同页选择、修改或重新查询时保留稳定位置。所选交易的原位凭证与移动面板展示同一组信息。

### 粒子、暂停与反馈

鼠标悬停在有值的柱形、环形扇区或预算行上时，粒子才开始流动。预算粒子仅显示在已使用的渐变条内。装饰图层不接收指针，并对辅助技术隐藏。系统减少动态效果时保留静态读数和预算状态。

操作提示使用可被播报的状态区，只在请求成功后显示；取消预算弹层或按 Escape 关闭时不显示“保存成功”。上传选中、拖入、处理中、出错和完成各有明确反馈。

**The Quiet Motion Rule.** 系统减少动态效果时，任务状态和最终读数仍然完整。

## Do's and Don'ts

### Do:

- **Do** 沿用蓝白画布、深蓝正文与系统 SF／苹方字体。
- **Do** 给图表提供指针、键盘和手机可用的读数路径。
- **Do** 为手机交互保留至少 44px 触摸目标，并避让底部安全区。
- **Do** 让新动效服从系统减少动态效果与离屏控制。
- **Do** 在确认成功后反馈结果，取消操作仅关闭当前界面。

### Don't:

- **Don't** 恢复历史绿色主操作或深色侧栏。
- **Don't** 用粒子、光晕、渐变或半透明底削弱正文对比。
- **Don't** 用色块或字母代替微信、支付宝的来源 SVG。
- **Don't** 将归集流程示意写成平台直连、公开注册或公开分享能力。
- **Don't** 在未经确认入账时把草稿混入月报，或把收支差额称为银行余额。
