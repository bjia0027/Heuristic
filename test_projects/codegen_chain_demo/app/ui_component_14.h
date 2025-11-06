#pragma once
#include "model_14.h"

class UIComponent14 {
public:
    UIComponent14();
    void render();
    void setModel(Model14* model);
private:
    Model14* model_;
};
