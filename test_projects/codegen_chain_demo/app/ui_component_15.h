#pragma once
#include "model_15.h"

class UIComponent15 {
public:
    UIComponent15();
    void render();
    void setModel(Model15* model);
private:
    Model15* model_;
};
