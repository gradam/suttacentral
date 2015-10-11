sc = window.sc || {};
sc.popup = {
    isPopupHover: false,
    popups: [],
    popup: function(location, popup, protected) {
        var self = this,
            offset,
            docWith,
            dupe,
            docWidth,
            isAbsolute = false,
            markupTarget = $(document.body),
            entered = false;
        if (self.isPopupHover) {
            return false
        }
        
        if (markupTarget.length == 0) {
            markupTarget = $('main');
            if (markupTarget.length == 0) {
                markupTarget = $('body');
            }
        }

        popup = $('<div class="text-popup"/>').append(popup);
        
        function align() {
            popup.removeAttr('style');
            if ('left' in location || 'top' in location) {
                offset = location
                offset.left = offset.left || 0
                offset.top = offset.top || 0
                location = document.body
                isAbsolute = true

            } else {
                location = $(location)
                offset = location.offset()
            }
            
            //We need to measure the doc width now.
            docWidth = $(document).width()
            // We need to create a dupe to measure it.
            dupe = $(popup).clone()
                
            markupTarget.append(dupe)
            var popupWidth = dupe.innerWidth(),
                popupHeight = dupe.innerHeight();
            dupe.remove()
            //The reason for the duplicity is because if you realize the
            //actual popup and measure that, then any transition effects
            //cause it to zip from it's original position...
            if (!isAbsolute) {
                offset.top += location.innerHeight() - popupHeight - location.outerHeight();
                offset.left -= popupWidth / 2;
            }

            if (offset.left < 1) {
                offset.left = 1;
                popup.innerWidth(popupWidth + 5);
            }
            
            if (offset.left + popupWidth + 5 > docWidth)
            {
                offset.left = docWidth - (popupWidth + 5);
            }
            popup.offset(offset)
            markupTarget.append(popup)
            if (offset.top < 0) {
                popup.height(popup.height() + offset.top);
                offset.top = 0;
                popup.css({'overflow-x': 'initial',
                           'overflow-y': 'scroll'}) 
            }
            popup.offset(offset)
            
        }
        
        align();
        popup.data('alignFn', align);
        popup.mouseenter(function(e) {
            self.isPopupHover = true
        });
        function removeIfNeeded() {
            if (protected) return
            var node = popup,
                visited = [];
            while (node) {
                if ($(node).is(':hover')) {
                    setTimeout(removeIfNeeded, 300);
                    return
                }
                node = $(node).data('parent');
                if (visited.indexOf(node) != -1) break
                visited.push(node);
            }
            popup.fadeOut(500);
            self.isPopupHover = false
        }
        setTimeout(function(){
            removeIfNeeded();
            popup.mouseleave(function(e){
                removeIfNeeded();
            }).mouseenter(function(e){
                entered = true;
                self.isPopupHover = true;
                popup.stop().fadeIn(0);
            });
        }, 1500)
        this.clear();
        
        if (protected) {
            popup.data('protected', protected);
        }
        this.popups.push(popup);
        return popup;
    },
    clear: function(clearProtected) {
        var keep = [];
        this.popups.forEach(function(e) {
            if (!clearProtected && e.data('protected')) {
                keep.push(e);
            } else {
                e.remove();
            }
        });
        this.popups = keep;
        this.isPopupHover = false;
        
    }
}