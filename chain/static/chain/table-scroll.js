document.documentElement.classList.add('js-enabled');

function setupTableTopScrollbars() {
    document.querySelectorAll('.table-wrap').forEach((tableWrap) => {
        if (tableWrap.dataset.topScrollReady === 'true') {
            return;
        }

        const topScroll = document.createElement('div');
        topScroll.className = 'table-scroll-top';
        topScroll.setAttribute('aria-hidden', 'true');

        const spacer = document.createElement('div');
        spacer.className = 'table-scroll-spacer';
        topScroll.appendChild(spacer);

        tableWrap.parentNode.insertBefore(topScroll, tableWrap);
        tableWrap.dataset.topScrollReady = 'true';

        const syncWidth = () => {
            spacer.style.width = `${tableWrap.scrollWidth}px`;
            topScroll.hidden = tableWrap.scrollWidth <= tableWrap.clientWidth;
        };

        const syncFromTop = () => {
            tableWrap.scrollLeft = topScroll.scrollLeft;
        };

        const syncFromTable = () => {
            topScroll.scrollLeft = tableWrap.scrollLeft;
        };

        topScroll.addEventListener('scroll', syncFromTop);
        tableWrap.addEventListener('scroll', syncFromTable);
        window.addEventListener('resize', syncWidth);

        syncWidth();
    });
}

function setupColumnControls() {
    document.querySelectorAll('[data-column-controls]').forEach((controls) => {
        const tableKey = controls.dataset.columnControls;
        const table = document.querySelector(`[data-column-table="${tableKey}"]`);
        const emptyMessage = document.querySelector(`[data-column-empty-message="${tableKey}"]`);

        if (!table || controls.dataset.columnControlsReady === 'true') {
            return;
        }

        controls.dataset.columnControlsReady = 'true';

        const toggles = Array.from(controls.querySelectorAll('[data-column-toggle]'));
        const setColumnVisibility = () => {
            const hasVisibleColumns = toggles.some((toggle) => toggle.checked);
            const tableWrap = table.closest('.table-wrap');
            const topScroll = tableWrap && tableWrap.previousElementSibling && tableWrap.previousElementSibling.classList.contains('table-scroll-top')
                ? tableWrap.previousElementSibling
                : null;

            toggles.forEach((toggle) => {
                const columnName = toggle.dataset.columnToggle;
                const cells = table.querySelectorAll(`[data-column="${columnName}"]`);

                cells.forEach((cell) => {
                    cell.classList.toggle('column-hidden', !toggle.checked);
                });
            });

            if (emptyMessage) {
                emptyMessage.hidden = hasVisibleColumns;
            }

            if (tableWrap) {
                tableWrap.hidden = !hasVisibleColumns;
            }

            if (topScroll && !hasVisibleColumns) {
                topScroll.hidden = true;
            }

            window.dispatchEvent(new Event('resize'));
        };

        toggles.forEach((toggle) => {
            toggle.addEventListener('change', setColumnVisibility);
        });

        setColumnVisibility();
    });
}

document.addEventListener('DOMContentLoaded', setupTableTopScrollbars);
document.addEventListener('DOMContentLoaded', setupColumnControls);
