# FlowLayout GUI components removed - only business logic and data processing remain

class BotView:
    """Bot data model class - contains business logic for bot management"""
    def __init__(self, homepath):
        self.name = 'bot0'
        self.homepath = homepath
        self.icon_path = homepath + '/resource/images/icons/c_robot64_0.png'
        self.actions = ['Edit', 'Clone', 'Delete']



class FlowLayout:
    """Flow layout algorithm - pure business logic for item arrangement"""
    
    def __init__(self, margin=0, spacing=5):
        self.margin = margin
        self.spacing = spacing
        self.itemList = []

    def add_item(self, item):
        """Add an item to the layout"""
        self.itemList.append(item)

    def remove_item(self, index):
        """Remove an item from the layout"""
        if 0 <= index < len(self.itemList):
            return self.itemList.pop(index)
        return None

    def get_item_count(self):
        """Get the number of items in the layout"""
        return len(self.itemList)

    def get_item(self, index):
        """Get an item by index"""
        if 0 <= index < len(self.itemList):
            return self.itemList[index]
        return None

    def calculate_layout(self, container_width, item_widths, item_heights):
        """
        Calculate the optimal layout for items in a flow arrangement
        Returns list of (x, y) positions for each item
        """
        positions = []
        x = self.margin
        y = self.margin
        line_height = 0
        
        for i, (width, height) in enumerate(zip(item_widths, item_heights)):
            # Check if item fits on current line
            if x + width + self.margin > container_width and i > 0:
                # Move to next line
                x = self.margin
                y += line_height + self.spacing
                line_height = 0
            
            positions.append((x, y))
            x += width + self.spacing
            line_height = max(line_height, height)
        
        return positions

    def calculate_total_height(self, container_width, item_widths, item_heights):
        """Calculate the total height needed for the layout"""
        positions = self.calculate_layout(container_width, item_widths, item_heights)
        if not positions:
            return 0
        
        max_y = max(y + h for (x, y), h in zip(positions, item_heights))
        return max_y + self.margin
