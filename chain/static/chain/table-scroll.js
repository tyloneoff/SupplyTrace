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

document.addEventListener('DOMContentLoaded', setupTableTopScrollbars);
