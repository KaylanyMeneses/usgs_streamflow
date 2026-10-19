# Relatório técnico: GPs para séries com faltantes e anomalias

Oct 18, 2026 · @Alisson Ursulino

## Problema

Queremos modelar uma série temporal real que apresenta, ao mesmo tempo, três comportamentos difíceis: valores faltantes, sazonalidade e picos anômalos. O objetivo é prever e reconstruir a série com incerteza e apontar os pontos anômalos.

- **Dados faltantes:** há instantes sem observação. Queremos reconstruí-los com intervalo de incerteza, sem imputar antes de modelar.
- **Sazonalidade:** a série repete um padrão com período aproximadamente fixo, sobreposto a uma tendência.
- **Picos anômalos:** alguns pontos fogem muito do padrão. Eles não podem distorcer o ajuste e devem ser detectados.
- **Dependência temporal:** o valor atual depende dos anteriores, então os pontos não são independentes.

Hipótese assumida: as falhas são MAR (o fato de faltar não depende do valor que faltou).

## Os três modelos e o que cada um resolve

Cada modelo fica com uma pessoa: o GP Student‑t trata os três problemas diretamente, o RGP‑t acrescenta dinâmica e o GPLVM entrega a densidade das janelas.

| Modelo | Faltantes | Sazonalidade | Anomalias | Papel no trabalho |
| --- | --- | --- | --- | --- |
| 1. GP com verossimilhança Student‑t e kernel Periódico × RBF + RBF | Sim: o instante faltante vira ponto de predição, com incerteza | Sim: kernel periódico; RBF longo para a tendência | Sim: cauda pesada ignora os picos; E\[τ\_i\] pequeno marca outlier | Núcleo: regressão probabilística e reconstrução |
| 2. RGP‑t (GP recorrente robusto) | Parcial: só os y observados entram no ELBO; os estados latentes cobrem todos os instantes | Indireta, pela dinâmica aprendida | Sim: mesma Student‑t com τ\_i | Modelo dinâmico: dinâmica não linear |
| 3. Bayesian GPLVM em janelas | Sim: dimensões ausentes saem da verossimilhança | Sim, se cada janela for um ciclo sazonal | Sim: janela com baixa densidade é candidata | Estimação de densidade (versão não linear do PPCA) |

Todos geram distribuições a posteriori aproximadas (variacionais) e intervalos de previsão. Os hiperparâmetros ficam como estimativas pontuais, otimizadas pela evidência.

A otimização Bayesiana (BoTorch) entra para escolher o que não é diferenciável: tamanho da janela, dimensão latente Q, número de pontos de indução M e graus de liberdade ν.

## Como estamos pensando em fazer

Cada pessoa fica com um modelo. Dados, avaliação, a função Student‑t e a otimização Bayesiana são compartilhados, para que os três resultados sejam comparáveis.

### Base comum (feita antes, por todos)

1. **Dados:** normalizar a série, marcar os faltantes com uma máscara e estimar o período sazonal pelo periodograma.
2. **Conjunto de avaliação único:** os mesmos pontos escondidos e as mesmas anomalias (rotuladas ou injetadas) para os três modelos.
3. **Formato de saída único:** para cada instante t, média, quantis de 2,5% e 97,5% e escore de anomalia. No modelo 3, o escore da janela é repassado aos instantes dela.
4. **Script de avaliação único:**
   - Reconstrução: RMSE, NLPD e cobertura empírica do intervalo de 95%, só em posições não anômalas.
   - Detecção: precisão, recall e AUC dos escores.
   - Baseline: GP com verossimilhança Gaussiana.

### Divisão por pessoa

| Pessoa | Modelo | Entregas | Carga | Plano B |
| --- | --- | --- | --- | --- |
| Pessoa 1 | GP Student‑t | Modelo 1, baseline Gaussiano e a função `student_t_elbo_terms` usada também pela Pessoa 2 | Baixa; por isso lidera a base comum | — |
| Pessoa 2 | RGP‑t | RNN de reconhecimento, camadas `DeepGPLayer`, ELBO completo; validar primeiro em dado sintético sem faltantes | Alta; começa assim que a função Student‑t estiver pronta | GP‑NARX com Student‑t (defasagens como entrada) |
| Pessoa 3 | Bayesian GPLVM em janelas | Janelas, máscara no ELBO, escore por janela; otimização Bayesiana (BoTorch) para os três modelos | Média | PPCA via EM com faltantes |

### Marcos

1. Base comum pronta: dados, avaliação e função Student‑t.
2. Cada modelo treinando em dado sintético com ground truth.
3. Cada modelo rodando no dado real, no formato de saída único.
4. Otimização Bayesiana, comparação entre os três e relatório.

## Implementação com GPyTorch

Tudo roda sobre GPyTorch; o que não existe pronto é código de "cola" em PyTorch: uma verossimilhança Student‑t customizada, a estrutura recorrente e o ELBO montado à mão.

| Peça | Nativo no GPyTorch | Escrito à mão |
| --- | --- | --- |
| GP esparso (pontos de indução, q(u), KL) | `ApproximateGP`, `VariationalStrategy` | — |
| Kernels periódico, RBF, soma e produto | `PeriodicKernel`, `RBFKernel`, `ScaleKernel` | — |
| Student‑t com τ\_i por ponto (escore de anomalia) | `StudentTLikelihood` existe, mas não expõe τ\_i | Função de ELBO com q(τ) em forma fechada (abaixo) |
| GPLVM | `BayesianGPLVM`, `VariationalLatentVariable` | Máscara de faltantes na verossimilhança |
| RGP‑t: camadas de transição | `DeepGPLayer` | — |
| RGP‑t: estados latentes, defasagens, propagação | — | RNN de reconhecimento (`torch.nn.GRU`), indexação, amostragem Monte Carlo |
| Otimização Bayesiana | BoTorch (construído sobre GPyTorch) | — |

### Modelo 1: GP esparso com kernel sazonal

```python
import gpytorch

class SeasonalSVGP(gpytorch.models.ApproximateGP):
    def __init__(self, Z, period):
        q_u = gpytorch.variational.CholeskyVariationalDistribution(Z.size(0))
        strat = gpytorch.variational.VariationalStrategy(self, Z, q_u, learn_inducing_locations=True)
        super().__init__(strat)
        per = gpytorch.kernels.PeriodicKernel()
        per.period_length = period                      # from the periodogram
        self.mean_module = gpytorch.means.ConstantMean()
        self.covar_module = (gpytorch.kernels.ScaleKernel(per * gpytorch.kernels.RBFKernel())   # seasonality
                             + gpytorch.kernels.ScaleKernel(gpytorch.kernels.RBFKernel()))     # trend

    def forward(self, t):
        return gpytorch.distributions.MultivariateNormal(self.mean_module(t), self.covar_module(t))
```

### Student‑t com τ\_i (modelos 1 e 2)

A Student‑t é escrita como mistura de Gaussianas: y\_i | f\_i, τ\_i \~ N(f\_i, σ²/τ\_i), com τ\_i \~ Gamma(ν/2, ν/2). Dado q(f\_i) = N(m\_i, v\_i), o q(τ\_i) ótimo tem forma fechada. Cada passo atualiza q(τ) e dá um passo de gradiente no GP, como no GP‑tVB.

```python
import math, torch
from torch.distributions import Gamma, kl_divergence

def student_t_elbo_terms(y, m, v, log_sigma2, nu):
    s2 = log_sigma2.exp()
    r = ((y - m) ** 2 + v) / s2
    a = torch.full_like(y, (nu + 1) / 2)              # optimal q(tau_i) = Gamma(a, b)
    b = (nu / 2 + r / 2).detach()
    E_tau, E_logtau = a / b, torch.digamma(a) - b.log()
    ell = -0.5 * torch.log(2 * math.pi * s2) + 0.5 * E_logtau - 0.5 * E_tau * r
    prior = Gamma(torch.full_like(a, nu / 2), torch.full_like(a, nu / 2))
    return ell.sum(), kl_divergence(Gamma(a, b), prior).sum(), E_tau   # small E_tau -> outlier

# training step: idx = minibatch of OBSERVED points only
out = model(t[idx])
ell, kl_tau, E_tau = student_t_elbo_terms(y[idx], out.mean, out.variance, log_sigma2, nu)
loss = -(N / len(idx)) * (ell - kl_tau) + model.variational_strategy.kl_divergence()
```

### Modelo 3: janelas e GPLVM

```python
import numpy as np

def make_windows(x, period):
    n = len(x) // period
    Y = x[: n * period].reshape(n, period)   # one row per seasonal cycle
    mask = ~np.isnan(Y)
    keep = mask.mean(axis=1) >= 0.5           # drop windows with >50% missing
    return Y[keep], mask[keep]
```

O GPLVM segue o tutorial de `BayesianGPLVM` do GPyTorch. A única mudança é multiplicar a log‑verossimilhança esperada por ponto pela máscara antes da soma no ELBO, com os NaN trocados por 0. O escore de anomalia por janela é o −ELBO da janela.

### Modelo 2: RGP‑t

Cada camada de transição é um `DeepGPLayer`. Uma `torch.nn.GRU` recebe a série (NaN → 0) e a máscara e devolve média e variância dos estados x\_t. As entradas de cada camada são os estados defasados \[x\_{t−1}, …, x\_{t−L}\], e a incerteza passa entre camadas por amostras reparametrizadas. A saída usa a mesma `student_t_elbo_terms`, e o ELBO soma os KL de u, x e τ.

## Ressalvas a declarar no trabalho

- **RGP‑t por Monte Carlo:** a incerteza passa entre camadas por amostras, não pelas estatísticas Ψ analíticas do REVARB‑t e do S‑REVARB. Herdamos do S‑REVARB a RNN de reconhecimento e o treino em minibatches.
- **Posterioris aproximadas:** a inferência variacional tende a subestimar a variância, e os hiperparâmetros são pontuais. Por isso medimos a cobertura empírica dos intervalos.
- **Janelas:** o embedding em janelas não está no material da disciplina. Janelas sobrepostas contariam a mesma evidência mais de uma vez, então usamos uma janela por ciclo.
- **Mecanismo de falta:** assumimos MAR. Se as falhas coincidirem com os eventos anômalos, essa hipótese quebra.
- **Ground truth:** se as anomalias forem injetadas, os resultados de detecção valem para esse tipo de pico, não para anomalias reais em geral.

## Referências

| Referência | Usada para | Situação |
| --- | --- | --- |
| [Mattos (2017), Recurrent Gaussian Processes and Robust Dynamical Modeling, tese, UFC](https://repositorio.ufc.br/ri/bitstream/riufc/25604/1/2017_tese_clcmattos.pdf) | Modelos 1 e 2: GP‑tVB (seção 4.1.1), RGP‑t e REVARB‑t (4.3–4.4) | Consultada |
| [Saul et al. (2016), Chained Gaussian Processes, AISTATS](https://proceedings.mlr.press/v51/saul16.html) | Modelo 1: Student‑t ignorando outliers (seção 4.2) | Consultada |
| [Rasmussen & Williams (2006), Gaussian Processes for Machine Learning](https://gaussianprocess.org/gpml/chapters/) | Modelo 1: kernels (cap. 4) e seleção de modelos (cap. 5) | Consultada |
| [Mattos et al. (2016), Recurrent Gaussian Processes, ICLR](https://arxiv.org/abs/1511.06644v1) | Modelo 2: base do RGP | No PDF de artigos |
| Mattos & Barreto (2019), A stochastic variational framework for Recurrent Gaussian Processes models, Neural Networks 112 | Modelo 2: S‑REVARB, RNN de reconhecimento e minibatches | No PDF de artigos |
| Lalchand, Ravuri & Lawrence, Generalised GPLVM with Stochastic Variational Inference | Modelo 3: GPLVM com faltantes | No PDF de artigos |
| Mattos et al. (2017), Deep recurrent Gaussian processes for outlier-robust system identification, Journal of Process Control 60 | Modelo 2: RGP‑t publicado | Conteúdo coberto pela tese |
| Mattos & Tobar (2021), The Art of Gaussian Processes, tutorial NeurIPS | Modelo 1: kernels e exemplo de reconstrução com faltantes | No material da disciplina |
| Titsias (2009), AISTATS; Hensman et al. (2013), UAI | GP esparso variacional e SVI | Citadas nos slides; não abertas |
| Salimbeni & Deisenroth (2017), Doubly Stochastic VI for Deep GPs, NeurIPS | Modelo 2: propagação por Monte Carlo | De memória; confirmar |
| Damianou et al. (2011), Variational Gaussian Process Dynamical Systems, NeurIPS | Modelo 3: priori temporal opcional em X | De memória; confirmar |
