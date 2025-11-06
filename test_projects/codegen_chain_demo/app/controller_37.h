#pragma once
#include "service_37.h"
#include "model_37.h"
#include <memory>

class Controller37 {
public:
    Controller37();
    void initialize();
    void run();
private:
    std::unique_ptr<Service37> service_;
    std::shared_ptr<Model37> model_;
};
