#pragma once
#include "model_16.h"

class UIComponent16 {
public:
    UIComponent16();
    void render();
    void setModel(Model16* model);
private:
    Model16* model_;
};
