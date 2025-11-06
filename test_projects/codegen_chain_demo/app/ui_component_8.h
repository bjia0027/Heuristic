#pragma once
#include "model_8.h"

class UIComponent8 {
public:
    UIComponent8();
    void render();
    void setModel(Model8* model);
private:
    Model8* model_;
};
