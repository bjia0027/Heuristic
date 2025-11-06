#include "service_35.h"

Service35::Service35() {}

void Service35::execute() {
    for (auto& cb : callbacks_) cb();
}

void Service35::registerCallback(std::function<void()> cb) {
    callbacks_.push_back(cb);
}
