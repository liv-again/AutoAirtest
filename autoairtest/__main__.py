"""命令行模块入口。

该文件使 `python -m autoairtest` 能够委托到统一 CLI 分发器。
入口层不承载业务逻辑，以保持命令解析、流程编排与领域模型之间的低耦合。
"""

from .cli import main


raise SystemExit(main())
