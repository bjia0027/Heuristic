#pragma once
#include "model_9.h"

class UIComponent9 {
public:
    UIComponent9();
    void render();
    void setModel(Model9* model);
private:
    Model9* model_;
};
