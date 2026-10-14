# 第三方资源与许可

根目录 MIT 协议适用于项目原创代码，不替代第三方代码的许可与版权声明。

`vendor/` 和 `public/assets/` 来自用户提供的 Claude 基础框架。原始资源来源为 https://bh.xingbox.me/ ，获取日期为 2026-10-14。框架只有编译产物，没有依赖锁文件；以下记录已识别的主要库，未确认版本的库不猜测版本。

| 组件 | 识别版本 | 上游 | 许可文本 |
| --- | --- | --- | --- |
| React / React DOM | 19.2.8 | https://github.com/facebook/react | [MIT](licenses/React-MIT.txt) |
| Chart.js | 4.5.1 | https://github.com/chartjs/Chart.js | [MIT](licenses/Chart.js-MIT.txt) |
| react-chartjs-2 | 未确认 | https://github.com/reactchartjs/react-chartjs-2 | [MIT](licenses/react-chartjs-2-MIT.txt) |
| @kurkle/color（Chart.js 颜色工具） | 未确认 | https://github.com/kurkle/color | [MIT](licenses/kurkle-color-MIT.txt) |
| Lucide 图标与组件 | 未确认 | https://github.com/lucide-icons/lucide | [ISC 及上游附带声明](licenses/Lucide-ISC.txt) |
| TanStack Router / Start | 未确认 | https://github.com/TanStack/router | [MIT](licenses/TanStack-Router-MIT.txt) |
| Seroval | 未确认 | https://github.com/lxsmnsyc/seroval | [MIT](licenses/Seroval-MIT.txt) |

许可文本从相应上游仓库获取并保留原始版权信息。重新构建前端时，请根据实际锁文件更新依赖清单和许可文本。
