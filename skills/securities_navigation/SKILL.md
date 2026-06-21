# Securities Navigation

证券 App 导航语义归一化技能。用于把测试用例中的业务简称转换为界面上可定位的文本。

## Rules

- `自选` maps to `我的自选`.
- `A股` and `沪深` map to `沪深京`.
- `国内指数更多` maps to `更多`.

## Boundaries

Do not claim that market data values are correct. Data correctness still requires human review unless an external oracle is available.
