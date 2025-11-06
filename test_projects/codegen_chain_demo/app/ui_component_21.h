#pragma once
#include "model_21.h"

class UIComponent21 {
public:
    UIComponent21();
    void render();
    void setModel(Model21* model);
private:
    Model21* model_;
};
