'''
Blind Source Separation using Tweaked Independent Vector Analysis with Auxiliary Function

2018 (c) Yaron Dibner & Virgile Hernicot, MIT License
'''
import numpy as np

from pyroomacoustics import stft, istft
from pyroomacoustics.bss.common import projection_back
from demix import *
from scipy.linalg import dft
from scipy.io import savemat
from sparir import SpaRIR

# A few contrast functions
f_contrasts = {
    'norm': {'f': (lambda r, c, m: c * r), 'df': (lambda r, c, m: c)},
    'cosh': {'f': (lambda r, c, m: m * np.log(np.cosh(c * r))), 'df': (lambda r, c, m: c * m * np.tanh(c * r))}
}


def sparseauxiva(X, S, n_iter, proj_back=True, return_filters=False, lasso=True):
    n_frames, n_freq, n_chan = X.shape

    k_freq = S.shape[0]

    # default to determined case
    n_src = n_chan

    # initialize the demixing matrices
    W = np.array([np.eye(n_chan, n_src) for f in range(n_freq)], dtype=X.dtype)

    f_contrast = f_contrasts['norm']
    f_contrast_args = [1, 1]

    I = np.eye(n_src, n_src)
    Y = np.zeros((n_frames, n_freq, n_src), dtype=X.dtype)
    V = np.zeros((n_freq, n_src, n_chan, n_chan), dtype=X.dtype)
    r = np.zeros((n_frames, n_src))
    G_r = np.zeros((n_frames, n_src))

    print("Init done, proceeding to sparse AuxIVA...")

    for epoch in range(n_iter):

        demix(Y, X, S, W)

        # simple loop as a start
        # shape: (n_frames, n_src)
        r[:, :] = np.sqrt(np.sum(np.abs(Y * np.conj(Y)), axis=1))

        # Apply derivative of contrast function
        G_r[:, :] = f_contrast['df'](r, *f_contrast_args) / r  # shape (n_frames, n_src)

        # Compute Auxiliary Variable
        for f in range(k_freq):
            for s in range(n_src):
                V[S[f], s, :, :] = (np.dot(G_r[None, :, s] * X[:, S[f], :].T, np.conj(X[:, S[f], :]))) / X.shape[0]

        # Update now the demixing matrix
        for f in range(k_freq):
            for s in range(n_src):
                WV = np.dot(np.conj(W[S[f], :, :].T), V[S[f], s, :, :])
                W[S[f], :, s] = np.linalg.solve(WV, I[:, s])
                W[S[f], :, s] /= np.sqrt(np.inner(np.conj(W[S[f], :, s]), np.dot(V[S[f], s, :, :], W[S[f], :, s])))

    print("Successfully computed the sparse weights, proceeding to lasso...")

    np.set_printoptions(precision=2)

    if lasso:
        if S[-1] == 2048:
            Sprim = S[0:-1]
        else:
            Sprim = S

        # Here comes Lassoooooooooo
        Z = np.zeros((n_src, k_freq), dtype=W.dtype)
        G = np.zeros((n_src, n_freq), dtype=Z.dtype)
        hrtf = np.zeros((n_freq, n_src), dtype=W.dtype)  # h in the time domain
        Hrtf = np.zeros((n_freq, n_src), dtype=W.dtype)  # H in the frequency domain
        DFT_matrix = dft(n_freq)
        # print(np.all(np.linalg.eigvals(DFT_matrix.T.dot(DFT_matrix)) > 0))
        for i in range(n_src):
            Z[i, :] = np.array([W[S[f], 0, i] / W[S[f], 1, i] for f in range(k_freq)]).conj().T
            G[i, S] = Z[i,:]
            # savemat('lasso.mat', dict(S=S, G=G))
            # plotVect(Z[i,:])
            # I believe in your case A is the DFT matrix of size |S| x F, and x is the h_rtf in the time domain.
            # hrtf[:, i] = lasso_admm(DFT_matrix[S, :], np.expand_dims(Z[i, :], axis=1), mu, QUIET=False, MAX_ITER=50)
            # hrtf[:, i] = ADMM(DFT_matrix[S, :], np.expand_dims(Z[i, :], axis=1))
            # print(hrtf[:,i].shape)
            # Then, after calculating hrtf you should transform it to the frequency domain to perform the demixing

            hrtf[:-1,i] = SpaRIR(np.expand_dims(G[i,0:-1],axis=1),Sprim)

            Hrtf[:, i] = np.dot(DFT_matrix, hrtf[:, i])
            # print(Hrtf[0, i])
            # Hrtf[:,i] = Z[i,:]
            # Finally, you could assemble W
            for f in range(n_freq):
                W[f, :, i] = np.conj([Hrtf[f, i], 1])

        print(hrtf[0])

    demix(Y, X, np.array(range(n_freq)), W)

    # Note: Remember applying projection_back in the end (in ../bss/.common.py) to solve the scale ambiguity

    if proj_back:
        z = projection_back(Y, X[:, :, 0])
        Y *= np.conj(z[None, :, :])

    if return_filters:
        return Y, W
    else:
        return Y
