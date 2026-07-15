# 施工资产与审计说明

## 1. 可复制资产

`assets/java/` 提供最小 Java 骨架：

- `ProjectModulith.java.template`：Modulith 结构入口。
- `open-module-package-info.java.template`：启动/装配等开放技术模块示例。
- `domain-package-info.java.template`：关闭的业务领域根包与允许依赖。
- `named-interface-package-info.java.template`：显式命名开放面。
- `ApplicationModulesTest.java.template`：结构验证测试。
- `DomainApi.java.template`：包含参数、返回值、异常和副作用语义的公开 API 示例。
- `DomainCommand.java.template`：包含业务字段与公开方法 Javadoc 的不可变命令示例。
- `DomainEvent.java.template`：使用 record component `@param` 的领域事件示例。

`assets/docs/` 提供领域 Spec、Validation 和渐进迁移 Plan。复制后删除不适用章节，不保留空占位符。

## 2. 使用顺序

1. 先完成领域识别和依赖裁决，不从模板里的示例名字反推领域。
2. 将模板复制到目标项目，再替换 `__PLACEHOLDER__`。
3. 根据目标工程已经验证的组件选择 `cn.mucang.simple.modulith` 或 Spring Modulith 注解，不混用。
4. 从目标项目 POM/依赖管理确认版本；模板不提供通用固定版本。
5. 补齐真实 `allowedDependencies` 和命名接口，禁止直接照抄示例依赖。
6. 为公开契约、POJO、字段、参数和核心方法补齐中文 Javadoc。
7. 先运行静态审计，再运行实际结构测试、编译、Javadoc 构建和行为测试。

## 3. 静态审计

```bash
python3 scripts/audit_java_modulith.py \
  --repo-root /path/to/project \
  --base-package cn.mucang.example \
  --fail-on warning
```

多模块工程可重复传入源码根：

```bash
python3 scripts/audit_java_modulith.py \
  --repo-root /path/to/project \
  --source-root service-app/src/main/java \
  --source-root service-app/src/test/java \
  --base-package cn.mucang.example
```

脚本检查：

- 是否存在 `@Modulithic` 入口和 `ApplicationModules.of(...).verify()` 结构测试。
- `@ApplicationModule` 领域根包是否有包级 Javadoc。
- 是否出现跨领域导入 `application / infrastructure / dao` 等内部包。
- 公开类型、POJO 字段、公开构造方法、公开/核心方法及其 `@param / @return / @throws` 是否有明显缺口。

可使用 `--format json` 接入 CI。脚本基于 Java 源码静态形状做快速审计，对复杂生成代码、非常规语法或语义质量可能出现漏报；最终门禁以项目编译、Javadoc 构建、Modulith 结构测试和人工评审为准。
