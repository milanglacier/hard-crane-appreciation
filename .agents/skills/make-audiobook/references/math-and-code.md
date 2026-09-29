# Speaking math and code

The listener has ears, not eyes. A formula spoken as a stream of symbols
("x sub t equals square root alpha bar sub t x sub zero plus …") is noise; a
formula spoken as a sentence about quantities is knowledge. Everything here is
in service of that difference. Exact symbols still matter for the reader who
glances at the screen, which is what `$$` display blocks are for.

## The three-beat pattern

For every formula that matters, in this order:

1. **Meaning.** What the quantities are and what the equation claims, in plain
   words, no symbols. "加噪到第 t 步的图片，其实就是原图缩小一点，再加一点高斯噪声。"
2. **Spoken formula.** The equation as a sentence, using the conventions below.
   "写成公式就是：x t 等于 根号 alpha bar t 乘以 x zero，加上 根号 1 减 alpha bar t 乘以 epsilon。"
3. **Exact display.** The LaTeX in a `$$` block right after the paragraph
   (shown only, never narrated).

```markdown
加噪到第 t 步的图片，其实就是原图缩小一点，再加一点高斯噪声。写成公式就是：
x t 等于 根号 alpha bar t 乘以 x zero，加上 根号 1 减 alpha bar t 乘以 epsilon。
这里的 epsilon 是标准正态噪声，alpha bar t 是一个从 1 慢慢降到 0 的数。

$$x_t = \sqrt{\bar\alpha_t}\,x_0 + \sqrt{1-\bar\alpha_t}\,\epsilon,\qquad \epsilon\sim\mathcal N(0, I)$$
```

Then **name the pieces** you will refer to again: "我们把 根号 alpha bar t 叫做
信号系数，把后面那一项叫做噪声项。" From then on, use the names, not the symbols.

Budget: one spoken formula should take under ~15 seconds. If it doesn't, split
it into named parts and speak the parts.

## Introducing notation

- Introduce a symbol once, with its type and role: "x zero 是干净图片，x t 是
  加了 t 步噪声之后的图片；t 从 1 到大 T，大 T 通常是一千。"
- Prefer meaningful names over letters where the field allows: "时间步"、"噪声
  预测网络" rather than "t"、"epsilon theta" every time.
- Mark case when it matters: "大 T" vs "小 t"; "大 N" for a matrix.
- Avoid double subscripts and primes in speech. Rename: "x t 减 1" is fine once;
  after that, "上一步的图片".
- Greek letters: alpha, beta, gamma, delta, epsilon, theta, lambda, mu, sigma,
  phi, psi, omega — spoken in English even in a Chinese book.

## Reading conventions — Chinese

| written                    | say                                              |
| -------------------------- | ------------------------------------------------ |
| `x_t`                      | x t （首次可说 "x 下标 t"）                        |
| `x_0`                      | x zero / x 零                                     |
| `\bar\alpha_t`             | alpha bar t                                       |
| `\hat y`                   | y hat                                             |
| `\tilde\mu`                | mu tilde                                          |
| `x^2`, `x^n`               | x 平方；x 的 n 次方                                |
| `\sqrt{a}`                 | 根号 a；根号下 a 加 b（多项时说"根号下"并在末尾停顿）|
| `\frac{a}{b}`              | a 除以 b （避免"分之"，中文顺序容易听反）           |
| `a \cdot b`, `ab`          | a 乘以 b；a 乘 b                                   |
| `\sum_{i=1}^{n} a_i`       | 对 i 从 1 到 n，把 a i 加起来 / 求和               |
| `\prod`                    | 连乘                                              |
| `\int f(x)\,dx`            | 对 f x 关于 x 积分 / 把 f 沿着 x 积分              |
| `\mathbb E[X]`             | X 的期望                                          |
| `\mathrm{Var}`             | 方差                                              |
| `p(x_t \mid x_{t-1})`      | 给定 x t 减 1 时，x t 的条件概率                    |
| `q(x_{1:T} \mid x_0)`      | 给定 x zero，整条加噪轨迹 x 1 到 x T 的分布          |
| `\mathcal N(\mu, \sigma^2)`| 均值 mu、方差 sigma 平方的高斯分布                  |
| `\sim`                     | 服从                                              |
| `\propto`                  | 正比于                                            |
| `\approx`                  | 约等于                                            |
| `:=`                       | 定义为                                            |
| `\nabla_\theta L`          | L 对 theta 的梯度                                  |
| `\partial L / \partial w`  | L 对 w 的偏导                                      |
| `\frac{d}{dt}`             | 对 t 求导                                          |
| `\|x\|^2`                  | x 的模长平方 / x 的二范数平方                       |
| `\arg\min_\theta`          | 让…最小的 theta                                    |
| `\log`, `\exp`             | log；e 的 … 次方                                   |
| `KL(q \| p)`               | q 和 p 之间的 KL 散度 / KL divergence               |
| `A^\top`, `A^{-1}`         | A 的转置；A 的逆                                    |
| `\in`, `\subset`           | 属于；包含于                                       |
| `\forall`, `\exists`       | 对所有的；存在                                     |
| `O(n \log n)`              | n log n 的复杂度 / 大 O n log n                     |

## Reading conventions — English

| written                    | say                                              |
| -------------------------- | ------------------------------------------------ |
| `x_t`                      | x t （first time: "x sub t"）                     |
| `\bar\alpha_t`             | alpha bar t                                       |
| `x^2`                      | x squared; x to the n                             |
| `\sqrt{a+b}`               | the square root of a plus b (pause)               |
| `\frac{a}{b}`              | a over b                                          |
| `\sum_{i=1}^n a_i`         | the sum over i from 1 to n of a i                 |
| `\int f(x)\,dx`            | the integral of f of x with respect to x          |
| `\mathbb E[X]`             | the expectation of X                              |
| `p(x_t \mid x_{t-1})`      | the probability of x t given x t minus one        |
| `\mathcal N(\mu,\sigma^2)` | a Gaussian with mean mu and variance sigma squared |
| `\nabla_\theta L`          | the gradient of L with respect to theta           |
| `\|x\|^2`                  | the squared norm of x                             |
| `\arg\min_\theta`          | the theta that minimizes                          |
| `:=`                       | is defined as                                     |

## Worked example: the DDPM simplified loss (depth 2)

```markdown
训练目标最后简化成一件很朴素的事：给网络一张加了噪声的图片和当前的时间步，
让它猜出刚才加进去的那个噪声是什么。猜得越准，loss 越小。

写成公式：loss 等于 epsilon 减去 epsilon theta 的模长平方，再对 t、x zero
和 epsilon 取期望。其中 epsilon theta 的输入是 x t 和 t。

$$L_{\text{simple}} = \mathbb E_{t,\,x_0,\,\epsilon}\Big[\,\big\lVert \epsilon - \epsilon_\theta(x_t, t)\big\rVert^2\Big]$$

注意这里没有任何 KL 散度、没有 ELBO 的影子。它们在推导里出现过，但最后都被
一个常数吸收掉了。这就是为什么 DDPM 的代码看起来像一个普通的回归问题。
```

Note what happened: no `{{…||…}}` overrides were needed, because the spoken
form is also readable on screen and the exact formula follows in a display
block. Reach for overrides only when the on-screen text must differ from the
spoken text inside the same sentence.

## Code

Never read code aloud token by token. The listener cannot hold indentation in
their head.

- **Describe the intent, then the shape.** "这个函数接收一个文件路径，返回
  文件里的所有行。签名很简单：输入是一个字符串切片，输出是一个 Result，成功时
  里面是 Vec of String。"
- **Show the exact code** in a fenced block immediately after; it is shown only.
- **Name at most two or three identifiers** in speech; the rest live in the
  block.
- **Identifiers**: read `read_to_string` as "read to string"; `snake_case`
  words separated by pauses; `camelCase` split naturally. Use `{{…||…}}` or the
  `pronunciations` map when the engine would stumble.
- **Symbols**: `&T` → "对 T 的引用"; `&mut T` → "对 T 的可变引用"; `->` →
  "返回"; `Option<T>` → "Option T"; `Vec<String>` → "Vec of String" or
  "String 的 Vec"; `impl Trait for Type` → "给 Type 实现 Trait"; `x?` → "问号
  运算符，出错就直接返回"; `::` — usually skip ("std fs read to string"); `==`
  → "等于"; `!=` → "不等于"; `&&`/`||` → "并且"/"或者"; `=>` → "映射到";
  `|x| x + 1` → "一个 closure，接收 x，返回 x 加 1".
- **Errors and output** can be quoted in speech when short ("编译器会说：
  borrow of moved value"), and shown exactly in a block.

````markdown
我们来写第一个会被借用检查器拒绝的程序。先创建一个 String，把它交给一个函数，
然后再打印它一次。编译器会说：borrow of moved value。

```rust
fn main() {
    let s = String::from("hello");
    takes(s);
    println!("{s}"); // error[E0382]: borrow of moved value: `s`
}
```

问题出在第三行。把 s 传给 takes 的时候，所有权已经跟着走了。
````

## Numbers and units

- Powers of two: "2 的 10 次方，也就是一千零二十四".
- Big-O: "n log n 的复杂度".
- Percentages and decimals: round in speech ("差不多 0.1"), exact in a
  display block only if the exact value carries meaning.
- Years, versions, step counts read fine as digits; leave them.

## Checklist before handing a math-heavy chapter to review

- Every `$$` block is preceded by prose that says the same thing in words.
- No bare inline `$…$` without an override or a `pronunciations` entry
  (`audiobook-stats` flags these).
- Every symbol used in speech was introduced in this chapter or the glossary.
- No spoken formula runs longer than ~15 seconds (~60 汉字).
- Code blocks are never the only place a fact appears.
