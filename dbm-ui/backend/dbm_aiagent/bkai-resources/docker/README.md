# DBM AIDEV 初始化镜像

默认基于 `bk-aidev-init:0.1.3`，可通过构建参数 `BKAI_INIT_IMAGE` 覆盖。

Skill Dockerfile 统一使用 `BKAI_SKILL_IMAGE_REPO` 作为仓库前缀，镜像名和版本保留在 Dockerfile 中。非空前缀必须以 `/` 结尾，例如：

```bash
export BKAI_SKILL_IMAGE_REPO=registry.example.com/team/
```

入口脚本通过 `--var BKAI_SKILL_IMAGE_REPO=...` 传给 bkai-init。未配置或为空时使用短镜像名，由目标平台按其镜像仓库配置处理。部署时请将原 `SKILL_BASE_IMAGE` 环境变量改为 `BKAI_SKILL_IMAGE_REPO`。
