"""Bayesian GPLVM utilities for streamflow windows and pointwise anomaly scores."""

import math

import gpytorch
import numpy as np
import torch
from torch.distributions import Gamma, Normal, StudentT, kl_divergence


def pca_init(Y, mask, latent_dim, device):
    y = torch.as_tensor(Y, dtype=torch.float32, device=device)
    m = torch.as_tensor(mask, dtype=torch.float32, device=device)
    col_mean = (y * m).sum(0) / m.sum(0).clamp_min(1.0)
    filled = torch.where(m > 0, y, col_mean.expand_as(y))
    centered = filled - filled.mean(0, keepdim=True)
    _, _, vh = torch.linalg.svd(centered, full_matrices=False)
    x = centered @ vh[:latent_dim].T
    return x / x.std(0, keepdim=True).clamp_min(1e-6)


class WindowBayesianGPLVM(gpytorch.models.gplvm.BayesianGPLVM):
    """One latent representation per window and one GP per window position."""

    def __init__(self, x_init, window, n_inducing):
        n_windows, latent_dim = x_init.shape
        prior_x = gpytorch.priors.NormalPrior(0.0, 1.0)
        latent_x = gpytorch.models.gplvm.VariationalLatentVariable(
            n_windows, window, latent_dim, x_init, prior_x
        )
        with torch.no_grad():
            latent_x.q_log_sigma.fill_(-2.0)

        inducing_idx = torch.randperm(n_windows, device=x_init.device)[:n_inducing]
        inducing = x_init[inducing_idx].unsqueeze(0).expand(window, -1, -1).clone()
        batch_shape = torch.Size([window])
        q_u = gpytorch.variational.CholeskyVariationalDistribution(
            n_inducing, batch_shape=batch_shape
        )
        strategy = gpytorch.variational.VariationalStrategy(
            self, inducing, q_u, learn_inducing_locations=True
        )
        super().__init__(latent_x, strategy)

        self.mean_module = gpytorch.means.ConstantMean(batch_shape=batch_shape)
        self.covar_module = gpytorch.kernels.ScaleKernel(
            gpytorch.kernels.RBFKernel(
                ard_num_dims=latent_dim, batch_shape=batch_shape
            ),
            batch_shape=batch_shape,
        )
        self.log_sigma2 = torch.nn.Parameter(
            torch.tensor(0.0, device=x_init.device)
        )

    def forward(self, x):
        return gpytorch.distributions.MultivariateNormal(
            self.mean_module(x), self.covar_module(x)
        )


def student_t_elbo_terms(y, mean, variance, log_sigma2, nu):
    sigma2 = log_sigma2.exp()
    residual = ((y - mean).square() + variance) / sigma2
    a = torch.full_like(y, (nu + 1.0) / 2.0)
    b = (nu / 2.0 + residual / 2.0).detach()
    expected_tau = a / b
    expected_log_tau = torch.digamma(a) - b.log()
    ell = (
        -0.5 * torch.log(2.0 * math.pi * sigma2)
        + 0.5 * expected_log_tau
        - 0.5 * expected_tau * residual
    )
    prior_tau = Gamma(torch.full_like(a, nu / 2.0), torch.full_like(a, nu / 2.0))
    kl_tau = kl_divergence(Gamma(a, b), prior_tau)
    return ell, kl_tau


def latent_distribution(latent, idx):
    scale = torch.nn.functional.softplus(latent.q_log_sigma[idx]) + 1e-6
    return Normal(latent.q_mu[idx], scale)


def std_normal_kl(q_x):
    return kl_divergence(
        q_x, Normal(torch.zeros_like(q_x.loc), torch.ones_like(q_x.scale))
    )


def train_gplvm(
    Y, mask, latent_dim, n_inducing, nu, epochs, batch_size, learning_rate=0.03,
    device="cpu",
):
    n_windows, window = Y.shape
    n_inducing = min(n_inducing, n_windows)
    device = torch.device(device)
    y_all = torch.as_tensor(Y, dtype=torch.float32, device=device)
    mask_all = torch.as_tensor(mask, dtype=torch.float32, device=device)
    model = WindowBayesianGPLVM(
        pca_init(Y, mask, latent_dim, device), window, n_inducing
    ).to(device)
    model.y_train, model.mask_train = y_all, mask_all
    optimizer = torch.optim.Adam(model.parameters(), lr=learning_rate)
    history = []
    n_visible = mask_all.sum().item()
    if n_visible <= 0:
        raise ValueError("O treino precisa conter ao menos uma célula visível.")

    for epoch in range(epochs):
        model.train()
        order = torch.randperm(n_windows, device=device)
        data_terms = 0.0
        for start in range(0, n_windows, batch_size):
            idx = order[start:start + batch_size]
            q_x = latent_distribution(model.X, idx)
            f_dist = model(q_x.rsample())
            y, observed = y_all[idx].T, mask_all[idx].T
            ell, kl_tau = student_t_elbo_terms(
                y, f_dist.mean, f_dist.variance, model.log_sigma2, nu
            )
            local = (
                ((ell - kl_tau) * observed).sum()
                - std_normal_kl(q_x).sum()
            )
            kl_u = model.variational_strategy.kl_divergence().sum()
            loss = -((n_windows / len(idx)) * local - kl_u)
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            data_terms += local.detach().item()
        kl_u = model.variational_strategy.kl_divergence().sum().detach().item()
        history.append((data_terms - kl_u) / n_visible)
        print(
            f"época {epoch + 1:02d}/{epochs} | "
            f"ELBO estimado/célula visível={history[-1]:.4f}"
        )
    model.eval()
    return model, history


def training_elbo_diagnostics(
    model, Y, mask, nu, batch_size=128, max_windows=2048, seed=1234,
):
    """Estimate training ELBO terms per observed cell on a seeded window sample."""
    device = next(model.parameters()).device
    y_all = torch.as_tensor(Y, dtype=torch.float32, device=device)
    mask_all = torch.as_tensor(mask, dtype=torch.float32, device=device)
    n_windows = len(y_all)
    total_visible = mask_all.sum().item()
    if n_windows == 0 or total_visible <= 0:
        raise ValueError("O diagnóstico requer janelas com células visíveis.")

    sample_count = min(n_windows, max_windows)
    torch.manual_seed(seed)
    indices = torch.randperm(n_windows, device=device)[:sample_count]
    was_training = model.training
    model.eval()
    model.variational_strategy._clear_cache()
    sums = {"log_likelihood": 0.0, "student_t_kl": 0.0, "latent_kl": 0.0}
    sample_visible = 0.0
    try:
        with torch.no_grad():
            for start in range(0, sample_count, batch_size):
                idx = indices[start:start + batch_size]
                q_x = latent_distribution(model.X, idx)
                f_dist = model(q_x.rsample())
                y, observed = y_all[idx].T, mask_all[idx].T
                ell, kl_tau = student_t_elbo_terms(
                    y, f_dist.mean, f_dist.variance, model.log_sigma2, nu
                )
                sums["log_likelihood"] += (ell * observed).sum().item()
                sums["student_t_kl"] += (kl_tau * observed).sum().item()
                sums["latent_kl"] += std_normal_kl(q_x).sum().item()
                sample_visible += observed.sum().item()
        if sample_visible <= 0:
            raise ValueError("A amostra selecionada não contém células visíveis.")
        scale = n_windows / sample_count
        kl_u = model.variational_strategy.kl_divergence().sum().item()
        estimated_local = scale * (
            sums["log_likelihood"] - sums["student_t_kl"] - sums["latent_kl"]
        )
        return {
            "janelas_amostradas": sample_count,
            "celulas_visiveis_amostradas": int(sample_visible),
            "log_likelihood_por_celula": sums["log_likelihood"] / sample_visible,
            "kl_student_t_por_celula": sums["student_t_kl"] / sample_visible,
            "kl_latente_por_celula": sums["latent_kl"] / sample_visible,
            "kl_inducao_por_celula": kl_u / total_visible,
            "elbo_estimado_por_celula": (estimated_local - kl_u) / total_visible,
        }
    finally:
        model.variational_strategy._clear_cache()
        model.train(was_training)


def nearest_train_latent(model, Y, mask, chunk=128, train_chunk=4096):
    device = next(model.parameters()).device
    y_new = torch.as_tensor(Y, dtype=torch.float32, device=device)
    m_new = torch.as_tensor(mask, dtype=torch.float32, device=device)
    y_tr, m_tr = model.y_train, model.mask_train
    picks = []
    with torch.no_grad():
        for start in range(0, len(y_new), chunk):
            y1 = y_new[start:start + chunk, None, :]
            m1 = m_new[start:start + chunk, None, :]
            best_dist = torch.full(
                (len(y1),), float("inf"), dtype=y_new.dtype, device=device
            )
            best_idx = torch.zeros(len(y1), dtype=torch.long, device=device)
            for train_start in range(0, len(y_tr), train_chunk):
                y_train = y_tr[train_start:train_start + train_chunk]
                m_train = m_tr[train_start:train_start + train_chunk]
                both = m1 * m_train[None]
                count = both.sum(-1)
                dist = ((y1 - y_train[None]).square() * both).sum(-1)
                dist = dist / count.clamp_min(1.0)
                dist = dist.masked_fill(count == 0, float("inf"))
                chunk_dist, chunk_idx = dist.min(dim=1)
                improved = chunk_dist < best_dist
                best_dist = torch.where(improved, chunk_dist, best_dist)
                best_idx = torch.where(
                    improved, chunk_idx + train_start, best_idx
                )
            picks.append(best_idx)
    return model.X.q_mu.detach()[torch.cat(picks)].clone()


def infer_new_windows(
    model, Y, mask, nu=4.0, epochs=15, batch_size=128, learning_rate=0.05,
):
    """Freeze GP parameters and fit only q(X), clearing GPyTorch prediction caches."""
    flags = {parameter: parameter.requires_grad for parameter in model.parameters()}
    was_training = model.training
    for parameter in model.parameters():
        parameter.requires_grad_(False)
    model.train()
    model.variational_strategy._clear_cache()
    try:
        n_windows, window = Y.shape
        latent = gpytorch.models.gplvm.VariationalLatentVariable(
            n_windows,
            window,
            model.X.latent_dim,
            nearest_train_latent(model, Y, mask),
            model.X.prior_x,
        ).to(next(model.parameters()).device)
        with torch.no_grad():
            latent.q_log_sigma.fill_(-2.0)
        optimizer = torch.optim.Adam(latent.parameters(), lr=learning_rate)
        device = next(model.parameters()).device
        y_all = torch.as_tensor(Y, dtype=torch.float32, device=device)
        mask_all = torch.as_tensor(mask, dtype=torch.float32, device=device)
        for _ in range(epochs):
            for start in range(0, n_windows, batch_size):
                idx = torch.arange(
                    start, min(start + batch_size, n_windows), device=device
                )
                q_x = latent_distribution(latent, idx)
                f_dist = model(q_x.rsample())
                y, observed = y_all[idx].T, mask_all[idx].T
                ell, kl_tau = student_t_elbo_terms(
                    y, f_dist.mean, f_dist.variance, model.log_sigma2, nu
                )
                per_window = (
                    ((ell - kl_tau) * observed).sum(dim=0)
                    - std_normal_kl(q_x).sum(dim=-1)
                )
                loss = -per_window.mean()
                optimizer.zero_grad()
                loss.backward()
                optimizer.step()
        return latent
    finally:
        model.variational_strategy._clear_cache()
        for parameter, flag in flags.items():
            parameter.requires_grad_(flag)
        model.train(was_training)


def predict_windows(
    model, latent, Y, mask, nu=4.0, n_samples=50, batch_size=128,
):
    device = next(model.parameters()).device
    y_all = torch.as_tensor(Y, dtype=torch.float32, device=device)
    mask_all = torch.as_tensor(mask, dtype=torch.float32, device=device)
    means, lower, upper, scores, f_batches = [], [], [], [], []
    kl_u_share = (
        model.variational_strategy.kl_divergence().sum().detach() / model.X.n
    )
    sigma = model.log_sigma2.detach().exp().sqrt()
    model.eval()
    model.variational_strategy._clear_cache()
    with torch.no_grad():
        for start in range(0, len(Y), batch_size):
            idx = torch.arange(
                start, min(start + batch_size, len(Y)), device=device
            )
            q_x = latent_distribution(latent, idx)
            y, observed = y_all[idx].T, mask_all[idx].T
            draws_y, draws_f, elbos = [], [], []
            for _ in range(n_samples):
                f_dist = model(q_x.rsample())
                f = (
                    f_dist.mean
                    + f_dist.variance.clamp_min(1e-8).sqrt()
                    * torch.randn_like(f_dist.mean)
                )
                noise = StudentT(df=f.new_tensor(nu)).rsample(f.shape) * sigma
                ell, kl_tau = student_t_elbo_terms(
                    y, f_dist.mean, f_dist.variance, model.log_sigma2, nu
                )
                draws_f.append(f.T)
                draws_y.append((f + noise).T)
                elbos.append(
                    ((ell - kl_tau) * observed).sum(dim=0)
                    - std_normal_kl(q_x).sum(dim=-1)
                    - kl_u_share
                )
            pred = torch.stack(draws_y)
            f_batches.append(torch.stack(draws_f))
            means.append(pred.mean(0))
            lower.append(torch.quantile(pred, 0.025, dim=0))
            upper.append(torch.quantile(pred, 0.975, dim=0))
            visible_count = observed.sum(dim=0).clamp_min(1.0)
            scores.append(-torch.stack(elbos).mean(0) / visible_count)
    return {
        "media": torch.cat(means).cpu().numpy(),
        "q025": torch.cat(lower).cpu().numpy(),
        "q975": torch.cat(upper).cpu().numpy(),
        "escore_elbo": torch.cat(scores).cpu().numpy(),
        "f_samples": torch.cat(f_batches, dim=1).cpu().numpy(),
    }


def add_hidden_logp(prediction, block, model, nu=4.0):
    """Evaluate held-out normal values without passing unrelated NaNs to StudentT."""
    hidden = torch.as_tensor(block["hidden"], dtype=torch.bool)
    logp = torch.full(hidden.shape, float("nan"), dtype=torch.float32)
    if hidden.any():
        target = torch.as_tensor(block["Y_true"], dtype=torch.float32)
        f_s = torch.as_tensor(prediction["f_samples"], dtype=torch.float32)
        if target.shape != hidden.shape or f_s.shape[1:] != hidden.shape:
            raise ValueError(
                "Dimensões incompatíveis entre Y_true, hidden e amostras preditivas."
            )
        target_hidden = target[hidden]
        f_hidden = f_s.reshape(f_s.shape[0], -1)[:, hidden.reshape(-1)]
        if not torch.isfinite(target_hidden).all():
            raise ValueError("Y_true não finito em uma posição escondida.")
        scale = model.log_sigma2.detach().exp().sqrt().cpu()
        density = StudentT(df=nu, loc=f_hidden, scale=scale).log_prob(
            target_hidden.unsqueeze(0)
        )
        logp[hidden] = (
            torch.logsumexp(density, dim=0) - math.log(f_s.shape[0])
        )
    prediction["logp_hidden"] = logp.numpy()
    return prediction


def loo_point_scores(
    model, block, nu=4.0, chunk_windows=128, infer_epochs=8, n_samples=30,
    infer_batch_size=128,
):
    """Negative predictive log density per visible day, leaving that day out."""
    Y = np.asarray(block["Y"], dtype=np.float32)
    mask = np.asarray(block["mask"], dtype=np.float32)
    n_windows, window = Y.shape
    scores = np.full((n_windows, window), np.nan, dtype=np.float32)
    device = next(model.parameters()).device
    sigma = model.log_sigma2.detach().exp().sqrt()

    for day in range(window):
        eligible = np.flatnonzero(mask[:, day] > 0)
        n_chunks = math.ceil(len(eligible) / chunk_windows)
        for chunk_no, start in enumerate(
            range(0, len(eligible), chunk_windows), start=1
        ):
            indices = eligible[start:start + chunk_windows]
            y_masked = Y[indices].copy()
            m_masked = mask[indices].copy()
            target = y_masked[:, day].copy()
            y_masked[:, day] = 0.0
            m_masked[:, day] = 0.0
            latent = infer_new_windows(
                model,
                y_masked,
                m_masked,
                nu=nu,
                epochs=infer_epochs,
                batch_size=infer_batch_size,
            )
            model.eval()
            model.variational_strategy._clear_cache()
            target_t = torch.as_tensor(target, dtype=torch.float32, device=device)
            draws = []
            with torch.no_grad():
                q_x = latent_distribution(
                    latent, torch.arange(len(indices), device=device)
                )
                for _ in range(n_samples):
                    f_dist = model(q_x.rsample())
                    loc = f_dist.mean[day]
                    scale_f = f_dist.variance[day].clamp_min(1e-8).sqrt()
                    draws.append(loc + scale_f * torch.randn_like(loc))
                f_draws = torch.stack(draws)
                density = StudentT(df=nu, loc=f_draws, scale=sigma).log_prob(
                    target_t.unsqueeze(0)
                )
                scores[indices, day] = (
                    -(
                        torch.logsumexp(density, dim=0) - math.log(n_samples)
                    ).cpu().numpy()
                )
            del latent, q_x, f_draws, density
            if chunk_no == n_chunks or chunk_no % 25 == 0:
                print(f"dia {day + 1}/{window}: lote {chunk_no}/{n_chunks}")
    return scores
