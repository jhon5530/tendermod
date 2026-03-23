/**
 * task_polling.js — Generic Celery task polling utility for tendermod.
 *
 * Usage:
 *   pollTask(taskId, onSuccess, onFailure, intervalMs)
 *
 * onSuccess(result) is called with the task result object when status === 'SUCCESS'.
 * onFailure(errorMsg) is called with the error string when status === 'FAILURE'.
 */

function pollTask(taskId, onSuccess, onFailure, intervalMs) {
    intervalMs = intervalMs || 2500;

    var interval = setInterval(function () {
        fetch('/api/task-status/' + taskId + '/')
            .then(function (response) {
                if (!response.ok) {
                    throw new Error('HTTP ' + response.status);
                }
                return response.json();
            })
            .then(function (data) {
                if (data.status === 'SUCCESS') {
                    clearInterval(interval);
                    onSuccess(data.result);
                } else if (data.status === 'FAILURE') {
                    clearInterval(interval);
                    onFailure(data.error || 'Error desconocido');
                }
                // PENDING | STARTED | RETRY → seguir esperando
            })
            .catch(function (err) {
                clearInterval(interval);
                onFailure('Error de red: ' + err.message);
            });
    }, intervalMs);

    return interval; // caller can cancel manually if needed
}


/**
 * showSpinner(containerId)
 * Muestra un spinner Bootstrap dentro del contenedor indicado.
 */
function showSpinner(containerId) {
    var el = document.getElementById(containerId);
    if (!el) return;
    el.innerHTML =
        '<div class="d-flex align-items-center gap-2 text-secondary">' +
        '<div class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></div>' +
        '<span>Procesando...</span>' +
        '</div>';
}


/**
 * hideSpinner(containerId)
 * Limpia el contenedor del spinner.
 */
function hideSpinner(containerId) {
    var el = document.getElementById(containerId);
    if (el) el.innerHTML = '';
}


/**
 * showSuccess(containerId, message)
 * Muestra un mensaje de exito Bootstrap.
 */
function showSuccess(containerId, message) {
    var el = document.getElementById(containerId);
    if (!el) return;
    el.innerHTML =
        '<div class="alert alert-success alert-sm mb-0 py-1">' +
        '<i class="bi bi-check-circle me-1"></i>' + (message || 'Completado') +
        '</div>';
}


/**
 * showError(containerId, message)
 * Muestra un mensaje de error Bootstrap.
 */
function showError(containerId, message) {
    var el = document.getElementById(containerId);
    if (!el) return;
    el.innerHTML =
        '<div class="alert alert-danger alert-sm mb-0 py-1">' +
        '<i class="bi bi-exclamation-triangle me-1"></i>' + (message || 'Error') +
        '</div>';
}


/**
 * launchExtraction(sessionId, action, spinnerId, successMsg, onComplete)
 * Wrapper de alto nivel para los botones de extraccion del Paso 1.
 *
 * Hace POST AJAX a /analysis/<sessionId>/step1/extract/ con {action}
 * y luego hace polling hasta que termine.
 */
function launchExtraction(sessionId, action, spinnerId, successMsg, onComplete) {
    showSpinner(spinnerId);

    var csrfToken = document.querySelector('[name=csrfmiddlewaretoken]');
    var csrf = csrfToken ? csrfToken.value : getCookie('csrftoken');

    fetch('/analysis/' + sessionId + '/step1/extract/', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': csrf,
        },
        body: JSON.stringify({ action: action }),
    })
        .then(function (r) {
            if (!r.ok) throw new Error('HTTP ' + r.status);
            return r.json();
        })
        .then(function (data) {
            if (data.error) throw new Error(data.error);
            pollTask(
                data.task_id,
                function (result) {
                    showSuccess(spinnerId, successMsg || 'Completado');
                    if (typeof onComplete === 'function') onComplete(result);
                },
                function (errMsg) {
                    showError(spinnerId, 'Error: ' + errMsg);
                }
            );
        })
        .catch(function (err) {
            showError(spinnerId, 'Error al lanzar tarea: ' + err.message);
        });
}


/**
 * launchEvaluation(sessionId, action, payload, spinnerId, onComplete)
 * Wrapper para los botones de evaluacion del Paso 2.
 */
function launchEvaluation(sessionId, action, payload, spinnerId, onComplete) {
    showSpinner(spinnerId);

    var csrfToken = document.querySelector('[name=csrfmiddlewaretoken]');
    var csrf = csrfToken ? csrfToken.value : getCookie('csrftoken');

    var body = Object.assign({ action: action }, payload);

    fetch('/analysis/' + sessionId + '/step2/evaluate/', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': csrf,
        },
        body: JSON.stringify(body),
    })
        .then(function (r) {
            if (!r.ok) throw new Error('HTTP ' + r.status);
            return r.json();
        })
        .then(function (data) {
            if (data.error) throw new Error(data.error);
            pollTask(
                data.task_id,
                function (result) {
                    showSuccess(spinnerId, 'Evaluacion completada');
                    if (typeof onComplete === 'function') onComplete(result);
                },
                function (errMsg) {
                    showError(spinnerId, 'Error: ' + errMsg);
                }
            );
        })
        .catch(function (err) {
            showError(spinnerId, 'Error al lanzar evaluacion: ' + err.message);
        });
}


/**
 * getCookie(name) — lee una cookie por nombre (para CSRF token).
 */
function getCookie(name) {
    var cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        var cookies = document.cookie.split(';');
        for (var i = 0; i < cookies.length; i++) {
            var cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === name + '=') {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}
