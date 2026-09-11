# 嵌入式代码入口

当前触觉固件位于 [Tactile500 固件](README_App.md)。

本轮先看[四板首次烧录说明](先读我_四板首次烧录.md)：左12、右12、左32和右32各500帧/秒，
先测试32点短线新版。短线=新版，长线=旧版；用户实测位置表见[板型与通道映射](docs/BOARD_VARIANTS_AND_CHANNEL_MAP.md)。

请打开 [Tactile500.uvprojx](Project/MDK/Tactile500.uvprojx)，按实际左/右、12/32 点及长/短线选择 Target。六份已构建的 GNU HEX 位于 [build/gcc](烧录_OSR256_20260910)。

原 I2C_TwoBoardsPolling 示例名称已退休；旧工程和旧说明存放在嵌入式代码上一级的备份目录。Libraries、Boards、Documents 为原厂 SDK 资源，名称保持不变。

当前V2版本字节保持0x21。本轮新增板型/发包预算检查并重新构建、测试；本轮产物尚未上板测量，
传感器新数据率另行验收。历史0x21实机记录见[修订21说明](docs/REVISION_21_HARDWARE_FIX.md)。
详细变更和现场步骤见[改动与上板验收](docs/CHANGELOG_AND_BENCH_PLAN.md)。
