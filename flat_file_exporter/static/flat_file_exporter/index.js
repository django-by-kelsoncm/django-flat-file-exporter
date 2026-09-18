$(function () {
    var POLLING_INTERVAL_MS = 5000;

    function refreshCardStatus(card, payload) {
        // Enable/disable the download button according to the status
        var downloadBtn = card.find('[data-export-download]');
        if (downloadBtn.length) {
            if (payload.status.value === 5 && payload.download_url) { // 5 = GENERATED
                downloadBtn.removeClass('btn-secondary disabled').addClass('btn-primary');
                downloadBtn.removeAttr('tabindex aria-disabled');
                downloadBtn.attr('title', 'Download');
                downloadBtn.attr('href', payload.download_url);
            } else {
                downloadBtn.removeClass('btn-primary').addClass('btn-secondary disabled');
                downloadBtn.attr('tabindex', '-1').attr('aria-disabled', 'true');
                downloadBtn.attr('title', 'Download unavailable until processing finishes');
                downloadBtn.attr('href', '#');
            }
        }
        var badge = card.find('[data-export-status-badge]').first();
        if (badge.length) {
            badge
                .removeClass('badge-success badge-danger badge-warning badge-secondary')
                .addClass('badge-' + payload.status.color)
                .text(payload.status.display);
        }

        card.attr('data-export-status', payload.status.value);
        if (payload.done) {
            card.attr('data-poll-url', '');
        }

        // Update the additional fields
        if ('size' in payload) {
            var tamanhoEl = card.find('[data-export-size]');
            if (tamanhoEl.length) {
                tamanhoEl.text(formatFileSize(payload.size));
            }
        }
        if ('generation_finished_at' in payload) {
            var fimEl = card.find('[data-export-finished-at]');
            if (fimEl.length) {
                fimEl.text(formatDateTime(payload.generation_finished_at));
            }
        }
        if ('processing_time' in payload) {
            var tpEl = card.find('[data-export-processing-time]');
            if (tpEl.length) {
                tpEl.text(payload.processing_time ? formatDuration(payload.processing_time) : '');
            }
        }
        if ('upload_time' in payload) {
            var tuEl = card.find('[data-export-upload-time]');
            if (tuEl.length) {
                tuEl.text(payload.upload_time ? formatDuration(payload.upload_time) : '');
            }
        }
        if ('failed_at' in payload) {
            var dfEl = card.find('[data-export-failed-at]');
            if (dfEl.length) {
                dfEl.text(formatDateTime(payload.failed_at));
            }
        }
        if ('trashed_at' in payload) {
            var dlEl = card.find('[data-export-trashed-at]');
            if (dlEl.length) {
                dlEl.text(formatDateTime(payload.trashed_at));
            }
        }
        if ('failure_cause' in payload) {
            var cfEl = card.find('[data-export-failure-cause]');
            if (cfEl.length) {
                cfEl.text(payload.failure_cause || 'N/A');
            }
        }
        if ('failure_stack' in payload) {
            var sfEl = card.find('[data-export-failure-stack]');
            if (sfEl.length) {
                sfEl.text(payload.failure_stack || 'N/A');
            }
        }
    }

    // Format bytes as a human-readable size
    function formatFileSize(bytes) {
        if (typeof bytes !== 'number' || isNaN(bytes)) return '';
        if (bytes === 0) return '0 bytes';
        var sizes = ['bytes', 'KB', 'MB', 'GB', 'TB'];
        var i = Math.floor(Math.log(bytes) / Math.log(1024));
        return (bytes / Math.pow(1024, i)).toFixed(1) + ' ' + sizes[i];
    }

    // Format ISO dates as a friendly string
    function formatDateTime(isoString) {
        if (!isoString) return '';
        var date = new Date(isoString);
        if (isNaN(date.getTime())) return '';
        return date.toLocaleString('pt-BR');
    }

    // Format seconds as a friendly duration (e.g. 38m56s)
    function formatDuration(seconds) {
        if (typeof seconds !== 'number' || isNaN(seconds) || seconds <= 0) return '0s';
        var mins = Math.floor(seconds / 60);
        var secs = seconds % 60;
        var hrs = Math.floor(mins / 60);
        mins = mins % 60;

        var parts = [];
        if (hrs > 0) parts.push(hrs + 'h');
        if (mins > 0) parts.push(mins + 'm');
        if (secs > 0 || parts.length === 0) parts.push(secs + 's');

        return parts.join('');
    }

    function pollCardStatus(card) {
        var pollUrl = card.attr('data-poll-url');
        if (!pollUrl) {
            return Promise.resolve();
        }

        return fetch(pollUrl, {
            method: 'GET',
            headers: {
                Accept: 'application/json'
            },
            credentials: 'same-origin'
        })
            .then(function(response) {
                if (!response.ok) {
                    return null;
                }
                return response.json();
            })
            .then(function(payload) {
                if (!payload) {
                    return;
                }
                refreshCardStatus(card, payload);
            })
            .catch(function() {
                return null;
            });
    }

    function startPolling() {
        window.setInterval(function() {
            var cards = $('.js-card').filter(function() {
                var status = String($(this).attr('data-export-status') || '');
                return status === '0' || status === '1';
            });

            var promises = [];
            cards.each(function() {
                promises.push(pollCardStatus($(this)));
            });

            return Promise.all(promises);
        }, POLLING_INTERVAL_MS);
    }

    function getCardCheckboxes() {
        return $('.change_list_results input[type="checkbox"]');
    }

    function updateCheckboxToggleIcon() {
        var checkboxes = getCardCheckboxes();
        var toggleIcon = $('.checkbox-toggle i');

        if (!checkboxes.length) {
            toggleIcon.removeClass('fa-check-square fa-square').addClass('fa-square');
            return;
        }

        var allChecked = checkboxes.length === checkboxes.filter(':checked').length;

        if (allChecked) {
            toggleIcon.removeClass('fa-square').addClass('fa-check-square');
        } else {
            toggleIcon.removeClass('fa-check-square').addClass('fa-square');
        }
    }

    $(document).on('click', '.checkbox-toggle', function() {
        var checkboxes = getCardCheckboxes();
        var allChecked = checkboxes.length && checkboxes.length === checkboxes.filter(':checked').length;

        checkboxes.prop('checked', !allChecked).trigger('change');
        updateCheckboxToggleIcon();
    });

    $(document).on('change', '.change_list_results input[type="checkbox"]', function() {
        updateCheckboxToggleIcon();
    });

    updateCheckboxToggleIcon();

    function getVisibleCardFieldsCount() {
        var configuredValue = parseInt($('.js-exports-grid').data('visibleFields'), 10);

        if (Number.isNaN(configuredValue) || configuredValue < 1) {
            return 3;
        }

        return configuredValue;
    }

    function initializeCardFieldsVisibility() {
        var visibleFieldsCount = getVisibleCardFieldsCount();

        $('.js-card').each(function() {
            var card = $(this);
            var fields = card.find('.js-card-field');
            var toggleButton = card.find('.js-toggle-campos');

            fields.removeClass('d-none js-campo-extra');

            if (fields.length <= visibleFieldsCount) {
                toggleButton.addClass('d-none').attr('aria-expanded', 'false').text('Show more');
                return;
            }

            fields.each(function(index) {
                if (index >= visibleFieldsCount) {
                    $(this).addClass('d-none js-campo-extra');
                }
            });

            toggleButton
                .removeClass('d-none')
                .attr('aria-expanded', 'false')
                .text('Show more');
        });
    }

    $(document).on('click', '.js-toggle-campos', function() {
        var button = $(this);
        var card = button.closest('.js-card');
        var extraFields = card.find('.js-campo-extra');
        var isExpanded = button.attr('aria-expanded') === 'true';

        if (isExpanded) {
            extraFields.addClass('d-none');
            button.attr('aria-expanded', 'false').text('Show more');
        } else {
            extraFields.removeClass('d-none');
            button.attr('aria-expanded', 'true').text('Show less');
        }
    });

    initializeCardFieldsVisibility();

    $('#newExportModal').on('shown.bs.modal', function () {
        $(this).find('.js-primeiro-formulario').trigger('focus');
    });

    var selectedStatuses = [];
    var selectedKinds = [];

    $(document).on('keyup', '.dropdown-menu .autocomplete-search', function() {
        var searchTerm = $(this).val().toLowerCase();
        var container = $(this).closest('.dropdown-menu');
        var items = container.find('.filter-items .filter-item-situacao, .filter-items .filter-item-tipo');

        items.each(function() {
            var text = $(this).data('text').toLowerCase();
            if (text.includes(searchTerm)) {
                $(this).show();
            } else {
                $(this).hide();
            }
        });
    });

    $('.filter-item-situacao').each(function() {
        $(this).on('click', function(e) {
            e.preventDefault();
            e.stopImmediatePropagation();

            var value = String($(this).data('value'));
            var index = selectedStatuses.indexOf(value);

            if (index > -1) {
                selectedStatuses.splice(index, 1);
                $(this).removeClass('selected');
            } else {
                selectedStatuses.push(value);
                $(this).addClass('selected');
            }

            updateActiveFilters();

            return false;
        });
    });

    $('.filter-item-tipo').each(function() {
        $(this).on('click', function(e) {
            e.preventDefault();
            e.stopImmediatePropagation();

            var value = String($(this).data('value'));
            var index = selectedKinds.indexOf(value);

            if (index > -1) {
                selectedKinds.splice(index, 1);
                $(this).removeClass('selected');
            } else {
                selectedKinds.push(value);
                $(this).addClass('selected');
            }

            updateActiveFilters();

            return false;
        });
    });

    function updateActiveFilters() {
        $('.filter-item-situacao').each(function() {
            var value = String($(this).data('value'));
            if (selectedStatuses.indexOf(value) > -1) {
                $(this).addClass('hidden');
            } else {
                $(this).removeClass('hidden');
            }
        });

        $('.filter-item-tipo').each(function() {
            var value = String($(this).data('value'));
            if (selectedKinds.indexOf(value) > -1) {
                $(this).addClass('hidden');
            } else {
                $(this).removeClass('hidden');
            }
        });

        var badges = [];
        var hasFilters = false;

        var searchText = $('#search-input').val();
        if (searchText && searchText.trim() !== '') {
            hasFilters = true;
            badges.push('<span class="badge badge-warning">Busca: ' + searchText + ' <i class="fas fa-times" data-filter="search"></i></span>');
        }

        if (selectedStatuses.length > 0) {
            hasFilters = true;
            selectedStatuses.forEach(function(value) {
                var element = $('.filter-item-situacao[data-value="' + value + '"]');
                var text = element.data('text');

                if (text) {
                    badges.push('<span class="badge badge-info">Status: ' + text + ' <i class="fas fa-times" data-filter="situacao" data-value="' + value + '"></i></span>');
                }
            });
        }

        if (selectedKinds.length > 0) {
            hasFilters = true;
            selectedKinds.forEach(function(value) {
                var element = $('.filter-item-tipo[data-value="' + value + '"]');
                var text = element.data('text');

                if (text) {
                    badges.push('<span class="badge badge-success"Kind: ' + text + ' <i class="fas fa-times" data-filter="tipo" data-value="' + value + '"></i></span>');
                }
            });
        }

        if (hasFilters) {
            $('#filter-badges').html(badges.join(''));
            $('#clear-filters').removeClass('d-none');
        } else {
            $('#filter-badges').html('<span class="text-muted" style="font-size: 0.875rem;">No active filters</span>');
            $('#clear-filters').addClass('d-none');
        }
    }

    $('#search-input').on('keyup', function() {
        updateActiveFilters();
    });

    $(document).on('click', '#filter-badges .fa-times', function() {
        var filterType = $(this).data('filter');
        var filterValue = String($(this).data('value'));

        if (filterType === 'situacao') {
            var index = selectedStatuses.indexOf(filterValue);
            if (index > -1) {
                selectedStatuses.splice(index, 1);
            }
            $('.filter-item-situacao[data-value="' + filterValue + '"]').removeClass('selected');
        } else if (filterType === 'tipo') {
            var index = selectedKinds.indexOf(filterValue);
            if (index > -1) {
                selectedKinds.splice(index, 1);
            }
            $('.filter-item-tipo[data-value="' + filterValue + '"]').removeClass('selected');
        } else if (filterType === 'search') {
            $('#search-input').val('');
        }

        updateActiveFilters();
    });

    $('#clear-filters').on('click', function(e) {
        e.preventDefault();
        selectedStatuses = [];
        selectedKinds = [];
        $('.filter-item-situacao, .filter-item-tipo').removeClass('selected');
        $('#search-input').val('');
        updateActiveFilters();
    });

    $('.dropdown-menu a[data-format]').on('click', function(e) {
        e.preventDefault();
        var format = $(this).data('format');
        alert('Exportar para ' + format.toUpperCase() + ' - Funcionalidade a ser implementada');
    });

    // Disable/enable a card's actions and visual state
    function setCardDisabled(card, disabled) {
        if (disabled) {
            card.css({
                'opacity': '0.5',
                'pointer-events': 'none',
                'filter': 'grayscale(50%)'
            }).addClass('card-disabled');
            card.find('input, button, a').prop('disabled', true).addClass('disabled').attr('tabindex', '-1').attr('aria-disabled', 'true');
            if (!card.find('.overlay').length) {
                card.append('<div class="overlay"><i class="fas fa-2x fa-spinner fa-spin text-muted"></i></div>');
            }
        } else {
            card.css({
                'opacity': '',
                'pointer-events': '',
                'filter': ''
            }).removeClass('card-disabled');
            card.find('input, button, a').prop('disabled', false).removeClass('disabled').removeAttr('tabindex').removeAttr('aria-disabled');
            card.find('.overlay').remove();
        }
    }

    // Delete button handler
    $(document).on('click', '.btn-danger[title="Delete"]', function(e) {
        e.preventDefault();
        e.stopPropagation();

        var card = $(this).closest('.js-card');
        var exportName = card.find('.card-title').text().trim();
        var deleteUrl = card.attr('data-delete-url') || card.data('deleteUrl') || $(this).attr('data-delete-url') || $(this).data('deleteUrl');

        if (!deleteUrl) {
            return;
        }

        // Delete confirmation
        if (!confirm('Move the export "' + exportName + '" to the trash?')) {
            return;
        }

        // Disable every action on the card right away
        setCardDisabled(card, true);

        // Send the delete request
        $.ajax({
            url: deleteUrl,
            type: 'POST',
            headers: {
                'X-CSRFToken': getCookie('csrftoken')
            },
            dataType: 'json',
            success: function(data) {
                if (data.success) {
                    // Update the card with the new status
                    refreshCardStatus(card, {
                        id: data.id,
                        status: data.status,
                        done: true
                    });

                    // Show the success message
                    showNotification('success', 'Export moved to the trash');

                    // Remove the card after a short delay
                    setTimeout(function() {
                        card.fadeOut(function() {
                            $(this).parent().remove();
                        });
                    }, 1500);
                } else {
                    setCardDisabled(card, false);
                    showNotification('error', data.message || 'Error moving the export to the trash');
                }
            },
            error: function(xhr, status, error) {
                setCardDisabled(card, false);
                console.error('Error deleting the export:', error);
                showNotification('error', 'Error moving the export to the trash: ' + error);
            }
        });
    });

    // Read the CSRF cookie
    function getCookie(name) {
        var cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            var cookies = document.cookie.split(';');
            for (var i = 0; i < cookies.length; i++) {
                var cookie = cookies[i].trim();
                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    }

    // Show notifications
    function showNotification(type, message) {
        var alertClass = 'alert-' + (type === 'success' ? 'success' : 'danger');
        var alertHtml = '<div class="alert ' + alertClass + ' alert-dismissible fade show" role="alert" style="position: fixed; top: 20px; right: 20px; z-index: 9999; min-width: 300px;">' +
                        message +
                        '<button type="button" class="close" data-dismiss="alert" aria-label="Fechar"><span aria-hidden="true">&times;</span></button>' +
                        '</div>';

        $(alertHtml).appendTo('body').delay(4000).fadeOut(function() {
            $(this).remove();
        });
    }

    startPolling();
});
