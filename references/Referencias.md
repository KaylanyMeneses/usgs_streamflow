**Base comum aos três**

| Referência                                                                           | Para quê                                                   | Temos        |
| ------------------------------------------------------------------------------------ | ---------------------------------------------------------- | ------------ |
| Rasmussen & Williams (2006), _Gaussian Processes for Machine Learning_               | GP, kernels, seleção de modelos                            | sim (online) |
| Titsias (2009), _Variational Learning of Inducing Variables in Sparse GPs_ (AISTATS) | pontos de indução                                          | sim (PDF)    |
| Hensman, Fusi & Lawrence (2013), _Gaussian Processes for Big Data_ (UAI)             | ELBO por ponto, minibatches, verossimilhança não Gaussiana | sim (PDF)    |
| Gardner et al. (2018), _GPyTorch_ (NeurIPS)                                          | implementação                                              | sim (PDF)    |

**Modelo 1, GP Student‑t**

| Referência                                                                                          | Para quê                          | Temos        |
| --------------------------------------------------------------------------------------------------- | --------------------------------- | ------------ |
| Mattos (2017), tese _Recurrent Gaussian Processes and Robust Dynamical Modeling_ (UFC), seção 4.1.1 | GP‑tVB: Student‑t com τ por ponto | sim (online) |
| Saul et al. (2016), _Chained Gaussian Processes_ (AISTATS)                                          | Student‑t ignorando outliers      | sim (online) |

**Modelo 2, RGP‑t**

| Referência                                                                                               | Para quê                                               | Temos                                      |
| -------------------------------------------------------------------------------------------------------- | ------------------------------------------------------ | ------------------------------------------ |
| Mattos et al. (2016), _Recurrent Gaussian Processes_ (ICLR)                                              | o RGP e o REVARB                                       | sim (PDF)                                  |
| Mattos et al. (2017), _Deep Recurrent GPs for Outlier‑Robust System Identification_ (J. Process Control) | o RGP‑t (versão robusta)                               | conteúdo coberto pela tese, seções 4.3–4.4 |
| Mattos & Barreto (2019), _A Stochastic Variational Framework for RGP Models_ (Neural Networks)           | S‑REVARB: GRU de reconhecimento e minibatches          | sim (PDF)                                  |
| Salimbeni & Deisenroth (2017), _Doubly Stochastic VI for Deep GPs_ (NeurIPS)                             | propagação por Monte Carlo e média linear na transição | sim (PDF)                                  |

**Modelo 3, Bayesian GPLVM**

| Referência                                                                        | Para quê                                        | Temos        |
| --------------------------------------------------------------------------------- | ----------------------------------------------- | ------------ |
| Tipping & Bishop (1999), _Probabilistic PCA_ (JRSS‑B)                             | ponto de partida (PPCA)                         | sim (PDF)    |
| Lawrence (2005), GPLVM (JMLR)                                                     | o GPLVM                                         | sim (PDF)    |
| Titsias & Lawrence (2010), _Bayesian GPLVM_ (AISTATS)                             | a versão Bayesiana com ELBO                     | sim (PDF)    |
| Lalchand, Ravuri & Lawrence (2022), _Generalised GPLVM with SVI_ (AISTATS)        | SVI e faltantes por máscara; é a base do código | sim (PDF)    |
| Damianou, Titsias & Lawrence (2011), _Variational GP Dynamical Systems_ (NeurIPS) | extensão temporal (opcional)                    | sim (PDF)    |
| Tutorial do GPyTorch, _GPLVM with SVI_                                            | implementação                                   | sim (online) |

**Avaliação**

| Referência                                | Para quê                             | Temos        |
| ----------------------------------------- | ------------------------------------ | ------------ |
| Gneiting & Raftery (2007) (JASA)          | interval score                       | sim (PDF)    |
| Vovk, Gammerman & Shafer (2005)           | conformal prediction                 | sim (PDF)    |
| Gibbs & Candès (2021) (NeurIPS)           | conformal adaptativo                 | sim (PDF)    |
| Esquema da coleção `daily` da API da USGS | qualificadores e status de aprovação | sim (online) |

**Para o forecast, se adotarmos a tarefa**, as referências do RGP (Mattos 2016 e 2019) já descrevem a simulação livre. Para o GP, Rasmussen & Williams basta.

Das que estão só citadas, as que mais vale ter em mãos são Titsias & Lawrence (2010), para o modelo 3, e Titsias (2009), para a base de todos.
